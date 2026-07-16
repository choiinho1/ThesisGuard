from __future__ import annotations

from datetime import datetime

import pytest

from thesisguard_backend.mcp_tools import market


def _epoch(year: int, month: int, day: int, hour: int = 12) -> int:
    return int(datetime(year, month, day, hour).timestamp())


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def __call__(self, *args, **kwargs) -> _FakeAsyncClient:
        return self

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False

    async def get(self, *args, **kwargs) -> _FakeResponse:
        return _FakeResponse(self._payload)


def _payload_with_stale_daily_bar() -> dict:
    """Last daily bar is 07-13; `meta` reflects a live 07-14 session already
    trading past yesterday's close, high, and volume."""
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "regularMarketTime": _epoch(2026, 7, 14),
                        "regularMarketPrice": 205.0,
                        "regularMarketDayHigh": 206.0,
                        "regularMarketDayLow": 201.0,
                        "regularMarketVolume": 50_000_000,
                        "chartPreviousClose": 203.53,
                    },
                    "timestamp": [_epoch(2026, 7, 10), _epoch(2026, 7, 13)],
                    "indicators": {
                        "quote": [
                            {
                                "open": [205.0, 208.0],
                                "high": [206.0, 210.57],
                                "low": [200.0, 203.0],
                                "close": [201.0, 203.53],
                                "volume": [100_000_000, 120_943_800],
                            }
                        ]
                    },
                }
            ]
        }
    }


@pytest.mark.asyncio
async def test_get_price_prefers_live_meta_over_stale_daily_bar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload_with_stale_daily_bar()
    monkeypatch.setattr(market.httpx, "AsyncClient", _FakeAsyncClient(payload))

    point = await market.get_price("NVDA")

    assert point is not None
    assert point.date == datetime(2026, 7, 14).date()
    assert point.close == 205.0
    assert point.high == 206.0
    assert point.low == 201.0
    assert point.volume == 50_000_000


@pytest.mark.asyncio
async def test_get_market_data_uses_live_price_for_change_pct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload_with_stale_daily_bar()
    monkeypatch.setattr(market.httpx, "AsyncClient", _FakeAsyncClient(payload))

    data = await market.get_market_data("NVDA")

    assert data.latest is not None
    assert data.latest.close == 205.0
    # baseline is the oldest bar in the (trimmed) history: close=201.0
    assert data.change_pct_30d == round((205.0 - 201.0) / 201.0 * 100, 2)


@pytest.mark.asyncio
async def test_get_price_falls_back_to_daily_bar_when_meta_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload_with_stale_daily_bar()
    del payload["chart"]["result"][0]["meta"]["regularMarketVolume"]
    monkeypatch.setattr(market.httpx, "AsyncClient", _FakeAsyncClient(payload))

    point = await market.get_price("NVDA")

    assert point is not None
    assert point.date == datetime(2026, 7, 13).date()
    assert point.close == 203.53
    assert point.volume == 120_943_800


@pytest.mark.asyncio
async def test_get_quote_computes_change_pct_against_prior_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload_with_stale_daily_bar()
    monkeypatch.setattr(market.httpx, "AsyncClient", _FakeAsyncClient(payload))

    quote = await market.get_quote("^GSPC")

    assert quote.ticker == "^GSPC"
    assert quote.price == 205.0
    assert quote.as_of == "2026-07-14"
    # prior day's close is 203.53 (the last daily bar, 07-13)
    assert quote.change_pct == round((205.0 - 203.53) / 203.53 * 100, 2)


@pytest.mark.asyncio
async def test_get_quote_returns_none_fields_when_fetch_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fetch_none(*args: object, **kwargs: object) -> dict | None:
        return None

    monkeypatch.setattr(market, "_fetch_chart_result", _fetch_none)

    quote = await market.get_quote("BTC-USD")

    assert quote.ticker == "BTC-USD"
    assert quote.price is None
    assert quote.change_pct is None
    assert quote.as_of is None
