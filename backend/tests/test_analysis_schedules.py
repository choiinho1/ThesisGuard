from __future__ import annotations

from datetime import UTC, datetime, time

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from thesisguard_backend import models as orm
from thesisguard_backend.db import Base
from thesisguard_backend.routers.analysis_schedules import (
    delete_schedule,
    get_schedule,
    put_schedule,
)
from thesisguard_backend.scheduler import compute_next_run_at
from thesisguard_backend.schemas import AnalysisScheduleRequest


def test_compute_next_run_at_same_day_when_still_ahead() -> None:
    after = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)  # 19:00 KST
    next_run = compute_next_run_at(time(21, 0), "Asia/Seoul", after=after)
    assert next_run == datetime(2026, 7, 14, 12, 0, tzinfo=UTC)  # 21:00 KST same day


def test_compute_next_run_at_rolls_to_next_day_once_past() -> None:
    after = datetime(2026, 7, 14, 13, 0, tzinfo=UTC)  # 22:00 KST, already past 21:00
    next_run = compute_next_run_at(time(21, 0), "Asia/Seoul", after=after)
    assert next_run == datetime(2026, 7, 15, 12, 0, tzinfo=UTC)  # 21:00 KST next day


def test_compute_next_run_at_can_run_immediately_during_selected_minute() -> None:
    after = datetime(2026, 7, 14, 12, 0, 46, tzinfo=UTC)  # 21:00:46 KST
    next_run = compute_next_run_at(
        time(21, 0),
        "Asia/Seoul",
        after=after,
        allow_current_minute=True,
    )
    assert next_run == after


def test_schedule_request_rejects_unknown_timezone() -> None:
    with pytest.raises(ValidationError):
        AnalysisScheduleRequest(daily_time=time(21, 0), timezone="Not/AZone")


def test_schedule_request_accepts_valid_timezone() -> None:
    request = AnalysisScheduleRequest(daily_time=time(21, 0), timezone="Asia/Seoul")
    assert request.timezone == "Asia/Seoul"


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_put_schedule_rejects_enabling_holding_without_thesis(db_session) -> None:
    user = orm.User(email="user@example.com", password_hash="hash")
    portfolio = orm.Portfolio(user=user, name="Test")
    holding = orm.Holding(portfolio=portfolio, ticker="NVDA", quantity=1, avg_buy_price=1)
    db_session.add(holding)
    await db_session.commit()

    payload = AnalysisScheduleRequest(daily_time=time(21, 0), timezone="Asia/Seoul")
    with pytest.raises(HTTPException) as caught:
        await put_schedule(payload, holding, db_session, user)
    assert caught.value.status_code == 400


@pytest.mark.asyncio
async def test_put_schedule_allows_saving_disabled_without_thesis(db_session) -> None:
    """A disabled schedule can be saved even before a thesis exists — only
    *enabling* auto-reanalysis requires one."""

    user = orm.User(email="user@example.com", password_hash="hash")
    portfolio = orm.Portfolio(user=user, name="Test")
    holding = orm.Holding(portfolio=portfolio, ticker="NVDA", quantity=1, avg_buy_price=1)
    db_session.add(holding)
    await db_session.commit()

    payload = AnalysisScheduleRequest(enabled=False, daily_time=time(21, 0), timezone="Asia/Seoul")
    response = await put_schedule(payload, holding, db_session, user)
    assert response.enabled is False


@pytest.mark.asyncio
async def test_put_schedule_creates_then_updates(db_session) -> None:
    user = orm.User(email="user@example.com", password_hash="hash")
    portfolio = orm.Portfolio(user=user, name="Test")
    holding = orm.Holding(portfolio=portfolio, ticker="NVDA", quantity=1, avg_buy_price=1)
    db_session.add(holding)
    await db_session.flush()
    thesis = orm.Thesis(
        holding_id=holding.id,
        raw_input="NVDA benefits from continued AI capex growth across hyperscalers.",
        main_thesis="AI capex tailwind",
    )
    db_session.add(thesis)
    await db_session.commit()

    created = await put_schedule(
        AnalysisScheduleRequest(daily_time=time(21, 0), timezone="Asia/Seoul"),
        holding,
        db_session,
        user,
    )
    assert created.ticker == "NVDA"
    assert created.recipient_email == "user@example.com"
    assert created.enabled is True

    updated = await put_schedule(
        AnalysisScheduleRequest(enabled=False, daily_time=time(9, 30), timezone="Asia/Seoul"),
        holding,
        db_session,
        user,
    )
    assert updated.id == created.id  # same row, not a duplicate
    assert updated.enabled is False
    assert updated.daily_time == time(9, 30)


@pytest.mark.asyncio
async def test_schedule_timestamps_remain_utc_aware_after_sqlite_round_trip(db_session) -> None:
    user = orm.User(email="utc@example.com", password_hash="hash")
    portfolio = orm.Portfolio(user=user, name="Test")
    holding = orm.Holding(portfolio=portfolio, ticker="CRDO", quantity=1, avg_buy_price=1)
    scheduled_for = datetime(2026, 7, 15, 6, 0, tzinfo=UTC)
    schedule = orm.AnalysisSchedule(
        holding=holding,
        enabled=True,
        daily_time=time(15, 0),
        timezone="Asia/Seoul",
        recipient_email=user.email,
        next_run_at=scheduled_for,
    )
    db_session.add(schedule)
    await db_session.commit()
    schedule_id = schedule.id

    db_session.expunge_all()
    restored = await db_session.get(orm.AnalysisSchedule, schedule_id)

    assert restored is not None
    assert restored.next_run_at == scheduled_for
    assert restored.next_run_at.tzinfo is UTC
    assert restored.next_run_at <= datetime(2026, 7, 15, 6, 1, tzinfo=UTC)


@pytest.mark.asyncio
async def test_get_and_delete_schedule_without_one_raises_404(db_session) -> None:
    user = orm.User(email="user@example.com", password_hash="hash")
    portfolio = orm.Portfolio(user=user, name="Test")
    holding = orm.Holding(portfolio=portfolio, ticker="NVDA", quantity=1, avg_buy_price=1)
    db_session.add(holding)
    await db_session.commit()

    with pytest.raises(HTTPException) as caught:
        await get_schedule(holding, db_session)
    assert caught.value.status_code == 404

    with pytest.raises(HTTPException) as caught:
        await delete_schedule(holding, db_session)
    assert caught.value.status_code == 404
