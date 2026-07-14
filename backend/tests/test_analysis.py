from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from thesisguard_backend import models as orm
from thesisguard_backend.db import Base
from thesisguard_backend.routers.analysis import get_latest_analysis


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
async def test_get_latest_analysis_requires_a_thesis(db_session) -> None:
    portfolio = orm.Portfolio(user=orm.User(email="u@example.com", password_hash="h"), name="T")
    holding = orm.Holding(portfolio=portfolio, ticker="NVDA", quantity=1, avg_buy_price=1)
    db_session.add(holding)
    await db_session.commit()

    with pytest.raises(HTTPException) as caught:
        await get_latest_analysis(holding, db_session)
    assert caught.value.status_code == 404


@pytest.mark.asyncio
async def test_get_latest_analysis_requires_a_completed_run(db_session) -> None:
    portfolio = orm.Portfolio(user=orm.User(email="u@example.com", password_hash="h"), name="T")
    holding = orm.Holding(portfolio=portfolio, ticker="NVDA", quantity=1, avg_buy_price=1)
    db_session.add(holding)
    await db_session.flush()
    db_session.add(orm.Thesis(holding_id=holding.id, raw_input="x" * 20, main_thesis="m"))
    await db_session.commit()

    with pytest.raises(HTTPException) as caught:
        await get_latest_analysis(holding, db_session)
    assert caught.value.status_code == 404


@pytest.mark.asyncio
async def test_get_latest_analysis_returns_only_the_newest_version_evidence(db_session) -> None:
    """Regression test: evidence must be scoped to the latest ThesisVersion,
    not every evidence row ever collected for the thesis (which accumulate
    across multiple /analyze runs). This also exercises thesis_version_id
    being set correctly at insert time (it depends on the version row being
    flushed first so its client-side UUID default is populated)."""

    portfolio = orm.Portfolio(user=orm.User(email="u@example.com", password_hash="h"), name="T")
    holding = orm.Holding(portfolio=portfolio, ticker="NVDA", quantity=1, avg_buy_price=1)
    db_session.add(holding)
    await db_session.flush()
    thesis = orm.Thesis(holding_id=holding.id, raw_input="x" * 20, main_thesis="m")
    db_session.add(thesis)
    await db_session.flush()

    version1 = orm.ThesisVersion(
        thesis_id=thesis.id,
        version_no=1,
        confidence_score=50,
        status="UNCHANGED",
        change_reason="first run",
    )
    db_session.add(version1)
    await db_session.flush()
    db_session.add(
        orm.Evidence(
            thesis_id=thesis.id,
            thesis_version_id=version1.id,
            document_id="doc-1",
            source_type="NEWS",
            content_snippet="old evidence",
            classification="NEUTRAL",
            impact="LOW",
            reason="r",
        )
    )
    db_session.add(
        orm.AnalysisResult(
            thesis_id=thesis.id,
            analysis_type="BULL_BEAR_JUDGE",
            bull_summary="b1",
            bear_summary="b1",
            judge_summary="j1",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    await db_session.commit()

    version2 = orm.ThesisVersion(
        thesis_id=thesis.id,
        version_no=2,
        confidence_score=55,
        status="UNCHANGED",
        change_reason="second run",
    )
    db_session.add(version2)
    await db_session.flush()  # required for version2.id to be populated below
    db_session.add(
        orm.Evidence(
            thesis_id=thesis.id,
            thesis_version_id=version2.id,
            document_id="doc-2",
            source_type="NEWS",
            content_snippet="new evidence",
            classification="SUPPORT",
            impact="HIGH",
            reason="r",
        )
    )
    db_session.add(
        orm.AnalysisResult(
            thesis_id=thesis.id,
            analysis_type="BULL_BEAR_JUDGE",
            bull_summary="b2",
            bear_summary="b2",
            judge_summary="j2",
            created_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
    )
    await db_session.commit()

    response = await get_latest_analysis(holding, db_session)

    assert response.version.version_no == 2
    assert response.analysis_result.judge_summary == "j2"
    assert [item.document_id for item in response.evidence] == ["doc-2"]
