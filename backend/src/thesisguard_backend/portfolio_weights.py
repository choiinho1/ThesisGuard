"""Current portfolio allocation calculated from market values."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Mapping, Sequence
from typing import Protocol

from thesisguard_backend.mcp_tools import market

_PRICE_TIMEOUT_SECONDS = 5


class WeightHolding(Protocol):
    id: uuid.UUID
    ticker: str
    quantity: float
    avg_buy_price: float
    current_weight: float


def calculate_current_weights(
    holdings: Sequence[WeightHolding],
    latest_prices: Mapping[str, float | None],
    *,
    cash_ratio: float,
) -> dict[uuid.UUID, float]:
    """Calculate market-value weights, using average cost when a quote is unavailable."""

    market_values: dict[uuid.UUID, float] = {}
    for holding in holdings:
        latest_price = latest_prices.get(holding.ticker.upper())
        price = (
            latest_price if latest_price is not None and latest_price > 0 else holding.avg_buy_price
        )
        market_values[holding.id] = max(0.0, holding.quantity) * max(0.0, price)

    total_market_value = sum(market_values.values())
    investable_ratio = max(0.0, min(100.0, 100.0 - cash_ratio))
    if total_market_value <= 0 or investable_ratio <= 0:
        return {holding.id: 0.0 for holding in holdings}

    weights = {
        holding_id: round(value / total_market_value * investable_ratio, 2)
        for holding_id, value in market_values.items()
    }
    # Keep the rounded stock weights plus cash at exactly 100%.
    largest_holding_id = max(market_values, key=market_values.get)  # type: ignore[arg-type]
    rounding_difference = round(investable_ratio - sum(weights.values()), 2)
    weights[largest_holding_id] = round(
        weights[largest_holding_id] + rounding_difference,
        2,
    )
    return weights


async def _get_latest_close(ticker: str) -> float | None:
    try:
        point = await asyncio.wait_for(
            market.get_price(ticker),
            timeout=_PRICE_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        return None
    return point.close if point is not None and point.close > 0 else None


async def refresh_current_weights(
    holdings: Sequence[WeightHolding],
    *,
    cash_ratio: float,
) -> bool:
    """Refresh in-memory ORM weights and report whether persistence is needed."""

    tickers = list(
        dict.fromkeys(holding.ticker.upper() for holding in holdings if holding.quantity > 0)
    )
    prices = await asyncio.gather(*(_get_latest_close(ticker) for ticker in tickers))
    latest_prices = dict(zip(tickers, prices, strict=True))
    weights = calculate_current_weights(
        holdings,
        latest_prices,
        cash_ratio=cash_ratio,
    )

    changed = False
    for holding in holdings:
        weight = weights[holding.id]
        if abs(holding.current_weight - weight) < 0.005:
            continue
        holding.current_weight = weight
        changed = True
    return changed
