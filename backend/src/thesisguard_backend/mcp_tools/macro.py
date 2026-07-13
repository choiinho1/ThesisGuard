"""Macro MCP — FRED (Federal Reserve Economic Data) graph CSV endpoints (no API key)."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime

import httpx

from thesisguard_backend.config import get_settings

_SERIES = {
    "interest_rate": "FEDFUNDS",  # Effective Federal Funds Rate, monthly
    "treasury_yield": "DGS10",  # 10-Year Treasury Constant Maturity Rate, daily
    "cpi": "CPIAUCSL",  # Consumer Price Index, monthly
}


@dataclass(slots=True)
class MacroSeriesPoint:
    series_id: str
    as_of: date
    value: float


async def _latest(series_id: str) -> MacroSeriesPoint | None:
    base = get_settings().fred_base_url
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(base, params={"id": series_id})
            response.raise_for_status()
        rows = list(csv.DictReader(io.StringIO(response.text)))
        for row in reversed(rows):
            raw_value = row.get(series_id, ".")
            if raw_value not in (None, ".", ""):
                return MacroSeriesPoint(
                    series_id=series_id,
                    as_of=datetime.strptime(row["DATE"], "%Y-%m-%d").date(),
                    value=float(raw_value),
                )
        return None
    except (httpx.HTTPError, ValueError, KeyError):
        return None


async def get_interest_rate() -> MacroSeriesPoint | None:
    return await _latest(_SERIES["interest_rate"])


async def get_treasury_yield() -> MacroSeriesPoint | None:
    return await _latest(_SERIES["treasury_yield"])


async def get_cpi() -> MacroSeriesPoint | None:
    return await _latest(_SERIES["cpi"])
