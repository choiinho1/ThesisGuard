from __future__ import annotations

import pytest
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from thesisguard_backend import models as orm
from thesisguard_backend.db import Base
from thesisguard_backend.routers.holdings import create_holding
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
