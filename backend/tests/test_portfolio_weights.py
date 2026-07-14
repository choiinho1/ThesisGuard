from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace

import pytest

from thesisguard_backend.mcp_tools.market import PricePoint
from thesisguard_backend.portfolio_weights import (
    calculate_current_weights,
    refresh_current_weights,
)


def _holding(ticker: str, quantity: float, avg_buy_price: float):
    return SimpleNamespace(
        id=uuid.uuid4(),
        ticker=ticker,
        quantity=quantity,
        avg_buy_price=avg_buy_price,
        current_weight=0.0,
    )


def test_calculate_current_weights_uses_market_value_and_cash_ratio() -> None:
    first = _holding("AAA", 2, 10)
    second = _holding("BBB", 2, 10)

    weights = calculate_current_weights(
        [first, second],
        {"AAA": 20, "BBB": 30},
        cash_ratio=10,
    )

    assert weights[first.id] == 36
    assert weights[second.id] == 54
    assert sum(weights.values()) == 90


def test_calculate_current_weights_falls_back_to_average_buy_price() -> None:
    first = _holding("AAA", 1, 100)
    second = _holding("BBB", 1, 300)

    weights = calculate_current_weights(
        [first, second],
        {"AAA": None, "BBB": None},
        cash_ratio=0,
    )

    assert weights[first.id] == 25
    assert weights[second.id] == 75


@pytest.mark.asyncio
async def test_refresh_current_weights_updates_holdings_from_latest_prices(monkeypatch) -> None:
    first = _holding("AAA", 1, 100)
    second = _holding("BBB", 1, 100)

    async def fake_get_price(ticker: str):
        close = 25 if ticker == "AAA" else 75
        return PricePoint(
            date=date(2026, 7, 14),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1,
        )

    monkeypatch.setattr(
        "thesisguard_backend.portfolio_weights.market.get_price",
        fake_get_price,
    )

    changed = await refresh_current_weights([first, second], cash_ratio=0)

    assert changed is True
    assert first.current_weight == 25
    assert second.current_weight == 75
