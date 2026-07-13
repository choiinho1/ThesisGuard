"""Market MCP — quotes and price history via Yahoo Finance's public chart API (no key).

stooq.com's CSV endpoints were the original choice here, but as of 2026-07 they
sit behind a JavaScript bot-challenge and can no longer be scraped with a plain
HTTP request (verified with backend/scripts/check_agent_compat.py). Yahoo
Finance's unofficial `/v8/finance/chart/` endpoint has no such gate and needs
no API key, so it replaces stooq as the source here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import httpx

_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


@dataclass(slots=True)
class PricePoint:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(slots=True)
class MarketData:
    ticker: str
    latest: PricePoint | None
    change_pct_30d: float | None


async def _fetch_chart(ticker: str, range_: str, interval: str) -> list[PricePoint]:
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers=_HEADERS) as client:
            response = await client.get(
                _CHART_URL.format(ticker=ticker.upper()),
                params={"range": range_, "interval": interval},
            )
            response.raise_for_status()
            payload = response.json()

        result = payload["chart"]["result"][0]
        timestamps = result["timestamp"]
        quote = result["indicators"]["quote"][0]
        points: list[PricePoint] = []
        for i, ts in enumerate(timestamps):
            close = quote["close"][i]
            if close is None:
                continue
            points.append(
                PricePoint(
                    date=datetime.fromtimestamp(ts).date(),
                    open=quote["open"][i],
                    high=quote["high"][i],
                    low=quote["low"][i],
                    close=close,
                    volume=quote["volume"][i] or 0,
                )
            )
        return points
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        return []


async def get_price(ticker: str) -> PricePoint | None:
    points = await _fetch_chart(ticker, range_="5d", interval="1d")
    return points[-1] if points else None


async def get_price_history(ticker: str, days: int = 90) -> list[PricePoint]:
    # Yahoo's `range` must cover at least `days` calendar days; pad and let the
    # caller trim. 1y is the smallest bucket comfortably covering 90 trading days.
    range_ = "1y" if days > 30 else "3mo"
    points = await _fetch_chart(ticker, range_=range_, interval="1d")
    return points[-days:]


async def get_market_data(ticker: str) -> MarketData:
    history = await get_price_history(ticker, days=31)
    latest = history[-1] if history else None
    change_pct_30d = None
    if latest and len(history) >= 2:
        baseline = history[0]
        if baseline.close:
            change_pct_30d = round((latest.close - baseline.close) / baseline.close * 100, 2)
    return MarketData(ticker=ticker.upper(), latest=latest, change_pct_30d=change_pct_30d)
