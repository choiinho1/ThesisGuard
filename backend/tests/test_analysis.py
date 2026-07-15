from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from thesisguard_backend import models as orm
from thesisguard_backend.db import Base
from thesisguard_backend.routers.analysis import (
    get_evidence_history,
    get_latest_analysis,
    get_owned_evidence,
    save_evidence,
    unsave_evidence,
)


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


async def _make_owned_holding(db_session, *, ticker: str = "NVDA") -> orm.Holding:
    portfolio = orm.Portfolio(user=orm.User(email="u@example.com", password_hash="h"), name="T")
    holding = orm.Holding(portfolio=portfolio, ticker=ticker, quantity=1, avg_buy_price=1)
    db_session.add(holding)
    await db_session.flush()
    return holding


@pytest.mark.asyncio
async def test_evidence_history_only_returns_saved_entries(db_session) -> None:
    """Regression test for auto-saving HIGH/MEDIUM impact evidence to history:
    the history endpoint must only surface rows flagged saved_to_history=True
    (set automatically by run_analysis_and_save for HIGH/MEDIUM impact, or
    manually via save_evidence), never LOW-impact rows that were never saved."""

    holding = await _make_owned_holding(db_session)
    portfolio = await db_session.get(orm.Portfolio, holding.portfolio_id)
    thesis = orm.Thesis(holding_id=holding.id, raw_input="x" * 20, main_thesis="m")
    db_session.add(thesis)
    await db_session.flush()

    db_session.add(
        orm.Evidence(
            thesis_id=thesis.id,
            document_id="doc-high",
            source_type="NEWS",
            content_snippet="high impact",
            classification="SUPPORT",
            impact="HIGH",
            reason="r",
            saved_to_history=True,
        )
    )
    db_session.add(
        orm.Evidence(
            thesis_id=thesis.id,
            document_id="doc-low",
            source_type="NEWS",
            content_snippet="low impact",
            classification="NEUTRAL",
            impact="LOW",
            reason="r",
            saved_to_history=False,
        )
    )
    await db_session.commit()

    history = await get_evidence_history(portfolio, db_session)

    assert [entry.document_id for entry in history] == ["doc-high"]
    assert history[0].ticker == "NVDA"
    assert history[0].holding_id == holding.id
    assert history[0].saved_to_history is True


@pytest.mark.asyncio
async def test_save_and_unsave_evidence_toggles_history_flag(db_session) -> None:
    """Backs the manual "주요 근거로 저장" / "History에서 삭제" actions for
    evidence that wasn't auto-saved (e.g. LOW impact)."""

    holding = await _make_owned_holding(db_session)
    user = await db_session.get(orm.User, holding.portfolio.user_id)
    thesis = orm.Thesis(holding_id=holding.id, raw_input="x" * 20, main_thesis="m")
    db_session.add(thesis)
    await db_session.flush()
    evidence = orm.Evidence(
        thesis_id=thesis.id,
        document_id="doc-low",
        source_type="NEWS",
        content_snippet="low impact",
        classification="NEUTRAL",
        impact="LOW",
        reason="r",
    )
    db_session.add(evidence)
    await db_session.commit()
    assert evidence.saved_to_history is False

    owned = await get_owned_evidence(evidence.id, db_session, user)
    saved = await save_evidence(owned, db_session)
    assert saved.saved_to_history is True

    owned_again = await get_owned_evidence(evidence.id, db_session, user)
    await unsave_evidence(owned_again, db_session)
    await db_session.refresh(evidence)
    assert evidence.saved_to_history is False


@pytest.mark.asyncio
async def test_get_owned_evidence_rejects_other_users_evidence(db_session) -> None:
    holding = await _make_owned_holding(db_session)
    thesis = orm.Thesis(holding_id=holding.id, raw_input="x" * 20, main_thesis="m")
    db_session.add(thesis)
    await db_session.flush()
    evidence = orm.Evidence(
        thesis_id=thesis.id,
        document_id="doc-1",
        source_type="NEWS",
        content_snippet="s",
        classification="NEUTRAL",
        impact="LOW",
        reason="r",
    )
    db_session.add(evidence)
    other_user = orm.User(email="other@example.com", password_hash="h")
    db_session.add(other_user)
    await db_session.commit()

    with pytest.raises(HTTPException) as caught:
        await get_owned_evidence(evidence.id, db_session, other_user)
    assert caught.value.status_code == 404
