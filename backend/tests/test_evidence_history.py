from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from thesisguard_backend import models as orm
from thesisguard_backend.agent_adapters import BackendContextProvider
from thesisguard_backend.db import Base
from thesisguard_backend.evidence_history import (
    clear_evidence_history,
    refresh_evidence_history_file,
)
from thesisguard_backend.routers.analysis import run_analysis_and_save


@pytest.mark.asyncio
async def test_history_file_summarizes_db_and_deduplicates_documents(tmp_path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user = orm.User(email="history@example.com", password_hash="hash")
        portfolio = orm.Portfolio(user=user, name="History")
        holding = orm.Holding(portfolio=portfolio, ticker="NVDA", current_weight=100)
        thesis = orm.Thesis(
            holding=holding,
            raw_input="AI 데이터센터 투자가 장기적으로 반도체 수요를 확대한다.",
            main_thesis="AI 데이터센터 수요 성장",
            key_assumptions=["클라우드 CAPEX 증가"],
            confidence_score=5,
            status=orm.ThesisStatus.STRENGTHENED,
        )
        session.add(thesis)
        await session.flush()

        version = orm.ThesisVersion(
            thesis_id=thesis.id,
            version_no=1,
            confidence_score=5,
            status=orm.ThesisStatus.STRENGTHENED,
            change_reason="데이터센터 매출 성장 확인",
            observation_points=["다음 분기 CAPEX"],
        )
        session.add(version)
        await session.flush()
        session.add_all(
            [
                orm.Evidence(
                    thesis_id=thesis.id,
                    thesis_version_id=version.id,
                    document_id="doc-repeated",
                    source_type=orm.EvidenceSourceType.NEWS,
                    source_url="https://example.com/old",
                    content_snippet="이전 요약",
                    classification=orm.EvidenceClassification.SUPPORT,
                    impact=orm.EvidenceImpact.MEDIUM,
                    reason="이전 판단",
                    related_assumptions=["클라우드 CAPEX 증가"],
                    published_at=datetime(2026, 7, 1, tzinfo=UTC),
                    created_at=datetime(2026, 7, 1, tzinfo=UTC),
                ),
                orm.Evidence(
                    thesis_id=thesis.id,
                    thesis_version_id=version.id,
                    document_id="doc-repeated",
                    source_type=orm.EvidenceSourceType.NEWS,
                    source_url="https://example.com/new",
                    content_snippet="최신 중복 제거 요약",
                    classification=orm.EvidenceClassification.SUPPORT,
                    impact=orm.EvidenceImpact.HIGH,
                    reason="최신 판단",
                    related_assumptions=["클라우드 CAPEX 증가"],
                    published_at=datetime(2026, 7, 2, tzinfo=UTC),
                    created_at=datetime(2026, 7, 2, tzinfo=UTC),
                ),
            ]
        )
        session.add(
            orm.Evidence(
                thesis_id=thesis.id,
                thesis_version_id=version.id,
                document_id="doc-repeated",
                source_type=orm.EvidenceSourceType.NEWS,
                source_url="https://example.com/new?utm_source=repeat",
                content_snippet=(
                    "과거 분석에서 이미 반영된 동일 문서이므로 이번 판단에서 중복 제외했습니다."
                ),
                classification=orm.EvidenceClassification.NEUTRAL,
                impact=orm.EvidenceImpact.LOW,
                reason="동일 document_id의 과거 근거가 이미 현재 신뢰도에 반영되어 있습니다.",
                related_assumptions=[],
                published_at=datetime(2026, 7, 3, tzinfo=UTC),
                created_at=datetime(2026, 7, 3, tzinfo=UTC),
            )
        )
        session.add(
            orm.AnalysisResult(
                thesis_id=thesis.id,
                thesis_version_id=version.id,
                analysis_type=orm.AnalysisType.BULL_BEAR_JUDGE,
                judge_summary="CAPEX 흐름이 기존 스토리를 강화합니다.",
            )
        )
        await session.flush()
        await session.execute(update(orm.Evidence).values(saved_to_history=True))
        await session.commit()

        snapshot = await refresh_evidence_history_file(
            session,
            holding=holding,
            thesis=thesis,
            history_dir=tmp_path,
        )

    assert snapshot.path.exists()
    assert snapshot.path.read_text(encoding="utf-8") == snapshot.summary
    assert snapshot.document_ids == ["doc-repeated"]
    assert snapshot.source_urls == [
        "https://example.com/old",
        "https://example.com/new",
        "https://example.com/new?utm_source=repeat",
    ]
    assert snapshot.summary.count("document_id=doc-repeated") == 1
    assert "이번 판단에서 중복 제외" not in snapshot.summary
    assert "최신 중복 제거 요약" in snapshot.summary
    assert "이전 요약" not in snapshot.summary
    assert "서사 문맥 전용" in snapshot.summary
    assert "직접 다시 반영하면 안 됩니다" in snapshot.summary

    provider = BackendContextProvider(session_factory, history_dir=tmp_path)
    context = await provider.load_analysis_context(str(portfolio.id), str(holding.id))
    assert context.evidence_history_summary == snapshot.path.read_text(encoding="utf-8")
    assert context.evidence_history_document_ids == ["doc-repeated"]
    assert context.evidence_history_source_urls == snapshot.source_urls

    await engine.dispose()


@pytest.mark.asyncio
async def test_reanalysis_entry_preserves_saved_history_for_agent_context(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = (tmp_path / "reanalysis-history.db").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    class AnalysisEntryObserved(RuntimeError):
        pass

    async with session_factory() as session:
        user = orm.User(email="reanalysis-history@example.com", password_hash="hash")
        portfolio = orm.Portfolio(user=user, name="Reanalysis history")
        holding = orm.Holding(portfolio=portfolio, ticker="NVDA", current_weight=100)
        thesis = orm.Thesis(
            holding=holding,
            raw_input="AI infrastructure demand remains durable over the investment horizon.",
            main_thesis="AI infrastructure demand remains durable",
            key_assumptions=["Demand keeps growing"],
        )
        session.add(thesis)
        await session.flush()
        evidence = orm.Evidence(
            thesis_id=thesis.id,
            document_id="saved-before-reanalysis",
            source_type=orm.EvidenceSourceType.NEWS,
            source_url="https://example.com/saved-before-reanalysis",
            content_snippet="Demand increased before the new analysis.",
            classification=orm.EvidenceClassification.SUPPORT,
            impact=orm.EvidenceImpact.HIGH,
            reason="Supports demand.",
            related_assumptions=["Demand keeps growing"],
            saved_to_history=True,
        )
        session.add(evidence)
        await session.commit()

        provider = BackendContextProvider(session_factory, history_dir=tmp_path)

        async def inspect_history_at_workflow_entry(
            portfolio_id: str,
            holding_id: str,
            *,
            runnable_config=None,
        ):
            context = await provider.load_analysis_context(portfolio_id, holding_id)
            assert context.evidence_history_document_ids == ["saved-before-reanalysis"]
            assert "Demand increased before the new analysis." in context.evidence_history_summary
            async with session_factory() as verification_session:
                persisted = await verification_session.get(orm.Evidence, evidence.id)
                assert persisted is not None
                assert persisted.saved_to_history is True
            raise AnalysisEntryObserved

        async def keep_current_weights(*args, **kwargs) -> bool:
            return False

        async def keep_existing_agent(*args, **kwargs):
            return None

        @contextmanager
        def no_op_trace(*args, **kwargs):
            yield SimpleNamespace(runnable_config=None, set_output=lambda output: None)

        monkeypatch.setattr(
            "thesisguard_backend.routers.analysis.arun_analysis_workflow",
            inspect_history_at_workflow_entry,
        )
        monkeypatch.setattr(
            "thesisguard_backend.routers.analysis.refresh_current_weights",
            keep_current_weights,
        )
        monkeypatch.setattr(
            "thesisguard_backend.routers.analysis.observe_llm_operation",
            no_op_trace,
        )
        monkeypatch.setattr(
            "thesisguard_backend.routers.analysis.build_agent_from_settings",
            keep_existing_agent,
        )
        monkeypatch.setattr(
            "thesisguard_backend.routers.analysis.configure_agent",
            lambda agent: None,
        )

        with pytest.raises(AnalysisEntryObserved):
            await run_analysis_and_save(holding, session, user)

    await engine.dispose()


@pytest.mark.asyncio
async def test_clear_history_unsaves_evidence_and_removes_materialized_context(tmp_path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user = orm.User(email="clear-history@example.com", password_hash="hash")
        portfolio = orm.Portfolio(user=user, name="Clear history")
        holding = orm.Holding(portfolio=portfolio, ticker="NVDA", current_weight=100)
        thesis = orm.Thesis(
            holding=holding,
            raw_input="AI infrastructure demand remains durable over the investment horizon.",
            main_thesis="AI infrastructure demand remains durable",
            key_assumptions=["Demand keeps growing"],
        )
        session.add(thesis)
        await session.flush()
        evidence = orm.Evidence(
            thesis_id=thesis.id,
            document_id="saved-doc",
            source_type=orm.EvidenceSourceType.NEWS,
            content_snippet="Demand increased.",
            classification=orm.EvidenceClassification.SUPPORT,
            impact=orm.EvidenceImpact.HIGH,
            reason="Supports demand.",
            related_assumptions=["Demand keeps growing"],
            saved_to_history=True,
        )
        session.add(evidence)
        await session.commit()

        snapshot = await refresh_evidence_history_file(
            session,
            holding=holding,
            thesis=thesis,
            history_dir=tmp_path,
        )
        assert snapshot.path.exists()

        await clear_evidence_history(
            session,
            holding=holding,
            thesis=thesis,
            history_dir=tmp_path,
        )
        await session.refresh(evidence)

        assert evidence.saved_to_history is False
        assert not snapshot.path.exists()

    await engine.dispose()
