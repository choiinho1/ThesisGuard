from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from thesisguard_backend import agent_adapters
from thesisguard_backend import models as orm
from thesisguard_backend.mcp_tools.market import MarketData, PricePoint
from thesisguard_backend.routers.market import get_market_quote


@pytest.mark.asyncio
async def test_get_market_quote_maps_latest_price_point(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_snapshot(ticker: str) -> MarketData:
        assert ticker == "NVDA"
        return MarketData(
            ticker="NVDA",
            latest=PricePoint(
                date=date(2026, 7, 14),
                open=170.0,
                high=174.40,
                low=168.24,
                close=171.32,
                volume=42_810_000,
            ),
            change_pct_30d=6.8,
        )

    monkeypatch.setattr(agent_adapters, "get_market_snapshot", fake_snapshot)

    quote = await get_market_quote(
        "nvda", current_user=orm.User(email="user@example.com", password_hash="hash")
    )

    assert quote.ticker == "NVDA"
    assert quote.price == 171.32
    assert quote.day_high == 174.40
    assert quote.day_low == 168.24
    assert quote.volume == 42_810_000
    assert quote.change_pct_30d == 6.8


@pytest.mark.asyncio
async def test_get_market_quote_404s_when_no_data(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_snapshot(ticker: str) -> MarketData:
        return MarketData(ticker=ticker, latest=None, change_pct_30d=None)

    monkeypatch.setattr(agent_adapters, "get_market_snapshot", fake_snapshot)

    with pytest.raises(HTTPException) as caught:
        await get_market_quote(
            "ZZZZ", current_user=orm.User(email="user@example.com", password_hash="hash")
        )

    assert caught.value.status_code == 404


@pytest.mark.asyncio
async def test_get_market_quote_rejects_invalid_ticker() -> None:
    with pytest.raises(HTTPException) as caught:
        await get_market_quote(
            "not valid!", current_user=orm.User(email="user@example.com", password_hash="hash")
        )

    assert caught.value.status_code == 422
