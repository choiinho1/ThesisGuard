from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from thesisguard_backend import models as orm
from thesisguard_backend.db import Base
from thesisguard_backend.routers.alerts import delete_alert, list_alerts


@pytest.mark.asyncio
async def test_delete_alert_removes_own_alert() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user = orm.User(email="user@example.com", password_hash="hash")
        portfolio = orm.Portfolio(user=user, name="Test")
        session.add(portfolio)
        await session.flush()

        alert = orm.Alert(
            user=user,
            portfolio_id=portfolio.id,
            severity="MAJOR",
            delivery="IMMEDIATE",
            title="AVGO 투자 논리 약화",
            message="핵심 전제와 충돌하는 근거가 발견되었습니다.",
        )
        session.add(alert)
        await session.commit()

        await delete_alert(alert.id, session, user)

        remaining = await session.scalars(select(orm.Alert))
        assert remaining.first() is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_alert_rejects_other_users_alert() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        owner = orm.User(email="owner@example.com", password_hash="hash")
        other = orm.User(email="other@example.com", password_hash="hash")
        portfolio = orm.Portfolio(user=owner, name="Test")
        session.add(portfolio)
        await session.flush()

        alert = orm.Alert(
            user=owner,
            portfolio_id=portfolio.id,
            severity="MINOR",
            delivery="NONE",
            title="TSM 투자 논리 변동",
            message="영향이 제한적인 변경이 감지되었습니다.",
        )
        session.add(alert)
        await session.commit()

        with pytest.raises(HTTPException) as caught:
            await delete_alert(alert.id, session, other)

        assert caught.value.status_code == status.HTTP_404_NOT_FOUND

    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_alert_rejects_missing_alert() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user = orm.User(email="user@example.com", password_hash="hash")
        session.add(user)
        await session.commit()

        with pytest.raises(HTTPException) as caught:
            await delete_alert(uuid.uuid4(), session, user)

        assert caught.value.status_code == status.HTTP_404_NOT_FOUND

    await engine.dispose()


@pytest.mark.asyncio
async def test_list_alerts_excludes_manual_analysis_alerts() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user = orm.User(email="user@example.com", password_hash="hash")
        portfolio = orm.Portfolio(user=user, name="Test")
        session.add(portfolio)
        await session.flush()

        scheduled_alert = orm.Alert(
            user=user,
            portfolio_id=portfolio.id,
            severity="MAJOR",
            delivery="IMMEDIATE",
            title="자동 재분석 알림",
            message="스케줄러가 감지한 변경입니다.",
            is_scheduled=True,
        )
        manual_alert = orm.Alert(
            user=user,
            portfolio_id=portfolio.id,
            severity="MAJOR",
            delivery="IMMEDIATE",
            title="수동 재분석 알림",
            message="사용자가 직접 실행한 재분석입니다.",
            is_scheduled=False,
        )
        session.add_all([scheduled_alert, manual_alert])
        await session.commit()

        alerts = await list_alerts(session, user)

        assert [alert.id for alert in alerts] == [scheduled_alert.id]

    await engine.dispose()
