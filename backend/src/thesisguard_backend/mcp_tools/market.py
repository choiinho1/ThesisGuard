"""Market MCP — quotes and price history via stooq.com CSV endpoints (no API key)."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime

import httpx

from thesisguard_backend.config import get_settings


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


def _symbol(ticker: str) -> str:
    return f"{ticker.lower()}.us"


async def get_price(ticker: str) -> PricePoint | None:
    base = get_settings().stooq_base_url
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{base}/q/l/", params={"s": _symbol(ticker), "f": "sd2t2ohlcv", "h": "", "e": "csv"}
            )
            response.raise_for_status()
        rows = list(csv.DictReader(io.StringIO(response.text)))
        if not rows or rows[0].get("Close") in (None, "N/D"):
            return None
        row = rows[0]
        return PricePoint(
            date=datetime.strptime(row["Date"], "%Y-%m-%d").date(),
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
            volume=int(float(row["Volume"])),
        )
    except (httpx.HTTPError, ValueError, KeyError):
        return None


async def get_price_history(ticker: str, days: int = 90) -> list[PricePoint]:
    base = get_settings().stooq_base_url
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{base}/q/d/l/", params={"s": _symbol(ticker), "i": "d"})
            response.raise_for_status()
        rows = list(csv.DictReader(io.StringIO(response.text)))
        points = [
            PricePoint(
                date=datetime.strptime(row["Date"], "%Y-%m-%d").date(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=int(float(row["Volume"])),
            )
            for row in rows
            if row.get("Close") not in (None, "N/D")
        ]
        return points[-days:]
    except (httpx.HTTPError, ValueError, KeyError):
        return []


async def get_market_data(ticker: str) -> MarketData:
    history = await get_price_history(ticker, days=31)
    latest = history[-1] if history else None
    change_pct_30d = None
    if latest and len(history) >= 2:
        baseline = history[0]
        if baseline.close:
            change_pct_30d = round((latest.close - baseline.close) / baseline.close * 100, 2)
    return MarketData(ticker=ticker.upper(), latest=latest, change_pct_30d=change_pct_30d)
