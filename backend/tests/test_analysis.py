from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from thesisguard_backend import models as orm
from thesisguard_backend.db import Base
from thesisguard_backend.routers.analysis import (
    get_evidence_history,
    get_holding_evidence_history,
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
async def test_get_latest_analysis_distinguishes_new_and_past_evidence(db_session) -> None:
    """Past evidence keeps its assessment but is explicitly separated from new evidence."""

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
        confidence_score=0,
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
            classification="CONTRADICT",
            impact="MEDIUM",
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
        confidence_score=5,
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
        orm.Evidence(
            thesis_id=thesis.id,
            thesis_version_id=version2.id,
            document_id="doc-1",
            source_type="NEWS",
            content_snippet=(
                "과거 분석에서 이미 반영된 동일 문서이므로 이번 판단에서 중복 제외했습니다."
            ),
            classification="NEUTRAL",
            impact="LOW",
            reason="동일 document_id의 과거 근거가 이미 현재 신뢰도에 반영되어 있습니다.",
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
    assert [item.document_id for item in response.evidence] == ["doc-2", "doc-1"]
    new_evidence, past_evidence = response.evidence
    assert new_evidence.evidence_scope == "NEW"
    assert new_evidence.classification == "SUPPORT"
    assert new_evidence.impact == "HIGH"
    assert past_evidence.evidence_scope == "PAST"
    assert past_evidence.classification == "CONTRADICT"
    assert past_evidence.impact == "MEDIUM"


async def _make_owned_holding(db_session, *, ticker: str = "NVDA") -> orm.Holding:
    portfolio = orm.Portfolio(user=orm.User(email="u@example.com", password_hash="h"), name="T")
    holding = orm.Holding(portfolio=portfolio, ticker=ticker, quantity=1, avg_buy_price=1)
    db_session.add(holding)
    await db_session.flush()
    return holding


@pytest.mark.asyncio
async def test_evidence_history_groups_by_holding_and_excludes_unsaved(db_session) -> None:
    """Regression test for auto-saving HIGH/MEDIUM impact evidence to history:
    the portfolio-wide history endpoint must group entries per holding (so the
    frontend can render a per-ticker view whenever routing is decided) and
    only surface rows flagged saved_to_history=True — never LOW-impact rows
    that were never saved."""

    portfolio = orm.Portfolio(user=orm.User(email="u@example.com", password_hash="h"), name="T")
    nvda = orm.Holding(portfolio=portfolio, ticker="NVDA", quantity=1, avg_buy_price=1)
    aapl = orm.Holding(portfolio=portfolio, ticker="AAPL", quantity=1, avg_buy_price=1)
    db_session.add_all([nvda, aapl])
    await db_session.flush()
    nvda_thesis = orm.Thesis(holding_id=nvda.id, raw_input="x" * 20, main_thesis="m")
    aapl_thesis = orm.Thesis(holding_id=aapl.id, raw_input="y" * 20, main_thesis="m")
    db_session.add_all([nvda_thesis, aapl_thesis])
    await db_session.flush()

    db_session.add(
        orm.Evidence(
            thesis_id=nvda_thesis.id,
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
            thesis_id=nvda_thesis.id,
            document_id="doc-low",
            source_type="NEWS",
            content_snippet="low impact",
            classification="NEUTRAL",
            impact="LOW",
            reason="r",
            saved_to_history=False,
        )
    )
    db_session.add(
        orm.Evidence(
            thesis_id=aapl_thesis.id,
            document_id="doc-medium",
            source_type="NEWS",
            content_snippet="medium impact",
            classification="SUPPORT",
            impact="MEDIUM",
            reason="r",
            saved_to_history=True,
        )
    )
    await db_session.commit()

    history = await get_evidence_history(portfolio, db_session)

    assert {group.ticker for group in history} == {"NVDA", "AAPL"}
    nvda_group = next(group for group in history if group.ticker == "NVDA")
    aapl_group = next(group for group in history if group.ticker == "AAPL")
    assert nvda_group.holding_id == nvda.id
    assert [entry.document_id for entry in nvda_group.entries] == ["doc-high"]
    assert [entry.document_id for entry in aapl_group.entries] == ["doc-medium"]


@pytest.mark.asyncio
async def test_holding_evidence_history_scopes_to_one_holding(db_session) -> None:
    """The per-holding endpoint (for whenever the frontend lands on per-ticker
    routing) must only return that holding's saved evidence."""

    holding = await _make_owned_holding(db_session)
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
    await db_session.commit()

    history = await get_holding_evidence_history(holding, db_session)

    assert [entry.document_id for entry in history] == ["doc-high"]


@pytest.mark.asyncio
async def test_holding_evidence_history_empty_without_thesis(db_session) -> None:
    holding = await _make_owned_holding(db_session)
    await db_session.commit()

    history = await get_holding_evidence_history(holding, db_session)

    assert history == []


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
