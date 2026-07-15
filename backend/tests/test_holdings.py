from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from thesisguard_backend import models as orm
from thesisguard_backend.db import Base
from thesisguard_backend.mcp_tools.market import MarketData, PricePoint
from thesisguard_backend.routers import holdings as holdings_router
from thesisguard_backend.routers.holdings import create_holding, get_holding_market_snapshot
from thesisguard_backend.schemas import HoldingCreateRequest


@pytest.mark.asyncio
async def test_create_holding_rejects_duplicate_ticker_in_same_portfolio() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user = orm.User(email="user@example.com", password_hash="hash")
        portfolio = orm.Portfolio(user=user, name="Test")
        session.add(portfolio)
        await session.commit()

        payload = HoldingCreateRequest(ticker="crdo", quantity=1, avg_buy_price=10, target_weight=5)
        await create_holding(payload, portfolio, session)

        with pytest.raises(HTTPException) as caught:
            await create_holding(payload, portfolio, session)

        assert caught.value.status_code == status.HTTP_409_CONFLICT
        assert "이미" in caught.value.detail

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_holding_market_snapshot_maps_latest_price_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    monkeypatch.setattr(holdings_router, "get_market_snapshot", fake_snapshot)

    holding = orm.Holding(ticker="NVDA", quantity=40, avg_buy_price=118.2, target_weight=20)
    snapshot = await get_holding_market_snapshot(holding)

    assert snapshot.ticker == "NVDA"
    assert snapshot.current_price == 171.32
    assert snapshot.day_high == 174.40
    assert snapshot.day_low == 168.24
    assert snapshot.day_open == 170.0
    assert snapshot.volume == 42_810_000
    assert snapshot.change_pct_30d == 6.8
    assert snapshot.as_of == "2026-07-14"


@pytest.mark.asyncio
async def test_get_holding_market_snapshot_handles_missing_price_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_snapshot(ticker: str) -> MarketData:
        return MarketData(ticker=ticker, latest=None, change_pct_30d=None)

    monkeypatch.setattr(holdings_router, "get_market_snapshot", fake_snapshot)

    holding = orm.Holding(ticker="ZZZZ", quantity=1, avg_buy_price=1, target_weight=1)
    snapshot = await get_holding_market_snapshot(holding)

    assert snapshot.ticker == "ZZZZ"
    assert snapshot.current_price is None
    assert snapshot.as_of is None
    assert snapshot.day_high is None
    assert snapshot.volume is None
