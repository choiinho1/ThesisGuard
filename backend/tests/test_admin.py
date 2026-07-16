from __future__ import annotations

import pytest
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from thesisguard_backend import models as orm
from thesisguard_backend import settings_service
from thesisguard_backend.db import Base
from thesisguard_backend.deps import get_current_admin_user
from thesisguard_backend.observability import LangfuseTraceSummary
from thesisguard_backend.routers import admin as admin_router
from thesisguard_backend.routers.admin import (
    create_scenario,
    list_langfuse_traces,
    list_qa_logs,
    list_scenarios,
    list_settings,
    update_setting,
)
from thesisguard_backend.schemas import AppSettingUpdateRequest, EvalScenarioCreateRequest


async def _fresh_session_factory() -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_get_current_admin_user_rejects_non_admin() -> None:
    user = orm.User(email="user@example.com", password_hash="hash")
    with pytest.raises(HTTPException) as caught:
        await get_current_admin_user(user)
    assert caught.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_get_current_admin_user_accepts_admin() -> None:
    admin = orm.User(email="admin@example.com", password_hash="hash", role=orm.UserRole.ADMIN)
    assert await get_current_admin_user(admin) is admin


@pytest.mark.asyncio
async def test_list_settings_seeds_and_returns_defaults() -> None:
    session_factory = await _fresh_session_factory()
    admin = orm.User(email="admin@example.com", password_hash="hash", role=orm.UserRole.ADMIN)

    async with session_factory() as session:
        session.add(admin)
        await session.commit()

        rows = await list_settings(session, admin)

        keys = {row.key for row in rows}
        assert "scoring.impact_weight_high" in keys
        assert "scheduler.max_retries" in keys


@pytest.mark.asyncio
async def test_update_setting_roundtrip_and_cache_invalidation() -> None:
    session_factory = await _fresh_session_factory()
    admin = orm.User(email="admin@example.com", password_hash="hash", role=orm.UserRole.ADMIN)

    async with session_factory() as session:
        session.add(admin)
        await session.commit()

        original = await settings_service.aget_setting(session, "scheduler.max_retries")
        assert original == 2

        updated = await update_setting(
            "scheduler.max_retries", AppSettingUpdateRequest(value=5), session, admin
        )
        assert updated.value == {"v": 5}

        refreshed = await settings_service.aget_setting(session, "scheduler.max_retries")
        assert refreshed == 5


@pytest.mark.asyncio
async def test_update_setting_rejects_unknown_key() -> None:
    session_factory = await _fresh_session_factory()
    admin = orm.User(email="admin@example.com", password_hash="hash", role=orm.UserRole.ADMIN)

    async with session_factory() as session:
        session.add(admin)
        await session.commit()

        with pytest.raises(HTTPException) as caught:
            await update_setting("does.not.exist", AppSettingUpdateRequest(value=1), session, admin)
        assert caught.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_scenario_create_and_list() -> None:
    session_factory = await _fresh_session_factory()
    admin = orm.User(email="admin@example.com", password_hash="hash", role=orm.UserRole.ADMIN)

    async with session_factory() as session:
        session.add(admin)
        await session.commit()

        created = await create_scenario(
            EvalScenarioCreateRequest(
                name="NVDA capex 질문",
                category="portfolio_qa",
                question="NVDA 투자 논리 근거는?",
            ),
            session,
            admin,
        )
        assert created.id is not None

        scenarios = await list_scenarios(session, admin)
        assert [item.name for item in scenarios] == ["NVDA capex 질문"]


@pytest.mark.asyncio
async def test_list_qa_logs_filters_by_user() -> None:
    session_factory = await _fresh_session_factory()
    admin = orm.User(email="admin@example.com", password_hash="hash", role=orm.UserRole.ADMIN)
    other_user = orm.User(email="other@example.com", password_hash="hash")

    async with session_factory() as session:
        session.add_all([admin, other_user])
        await session.flush()
        portfolio = orm.Portfolio(user=other_user, name="Test")
        session.add(portfolio)
        await session.flush()
        session.add(
            orm.QaLog(
                user_id=other_user.id,
                portfolio_id=portfolio.id,
                question="이 포트폴리오 위험 요인은?",
                answer="집중 리스크가 있습니다.",
                evidence_document_ids=["doc-1"],
            )
        )
        await session.commit()

        logs = await list_qa_logs(session, admin)
        assert len(logs) == 1
        assert logs[0].user_email == "other@example.com"
        assert logs[0].evidence_document_ids == ["doc-1"]


@pytest.mark.asyncio
async def test_list_langfuse_traces_returns_fetched_summaries(monkeypatch) -> None:
    admin = orm.User(email="admin@example.com", password_hash="hash", role=orm.UserRole.ADMIN)
    fetched = [
        LangfuseTraceSummary(
            id="trace-1",
            name="thesisguard.analyze-holding",
            timestamp="2026-07-13T00:00:00Z",
            user_id="user-1",
            latency_seconds=4.2,
            total_cost=0.01,
            tags=["thesisguard"],
        )
    ]

    async def fake_alist_recent_traces(*, limit: int) -> list[LangfuseTraceSummary]:
        assert limit == 20
        return fetched

    monkeypatch.setattr(admin_router, "alist_recent_traces", fake_alist_recent_traces)

    result = await list_langfuse_traces(admin)
    assert result == fetched
