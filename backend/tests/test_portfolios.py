from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from thesisguard_backend import models as orm
from thesisguard_backend.db import Base
from thesisguard_backend.mcp_tools.market import PricePoint
from thesisguard_backend.routers.portfolios import get_dashboard


@pytest.mark.asyncio
async def test_dashboard_serializes_holding_after_weight_refresh(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def fake_get_price(_ticker: str) -> PricePoint:
        return PricePoint(
            date=date(2026, 7, 14),
            open=200,
            high=200,
            low=200,
            close=200,
            volume=1,
        )

    monkeypatch.setattr(
        "thesisguard_backend.portfolio_weights.market.get_price",
        fake_get_price,
    )

    async with session_factory() as session:
        user = orm.User(email="dashboard@example.com", password_hash="hash")
        portfolio = orm.Portfolio(user=user, name="Test", cash_ratio=0)
        holding = orm.Holding(
            portfolio=portfolio,
            ticker="NVDA",
            quantity=1,
            avg_buy_price=100,
            current_weight=0,
        )
        session.add(user)
        await session.commit()

        dashboard = await get_dashboard(portfolio.id, portfolio, session)

        assert dashboard.holdings[0].id == holding.id
        assert dashboard.holdings[0].current_weight == 100
        assert dashboard.holdings[0].updated_at is not None

    await engine.dispose()
