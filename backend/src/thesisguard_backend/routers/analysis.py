"""POST /api/holdings/{id}/analyze — the B<->C integration point.

Calls C's ``arun_analysis_workflow()``, persists every part of
``ThesisAnalysisResult`` across theses/thesis_versions/evidence/
analysis_results/alerts, and returns the same result to the caller.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated

from agents.graph import arun_analysis_workflow, configure_agent
from agents.logic_graph import normalize_logic_graph
from agents.models import AlertDecision, EvidenceImpact, EvidenceItem
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from thesisguard_backend import models as orm
from thesisguard_backend import settings_service
from thesisguard_backend.agent_adapters import build_agent_from_settings
from thesisguard_backend.alert_engine import handle_alert_decision
from thesisguard_backend.config import get_settings
from thesisguard_backend.db import session_factory
from thesisguard_backend.deps import Agent, CurrentUser, DbSession, get_owned_portfolio
from thesisguard_backend.evidence_history import (
    is_duplicate_placeholder,
    refresh_evidence_history_file,
    select_substantive_evidence,
)
from thesisguard_backend.observability import observe_llm_operation
from thesisguard_backend.portfolio_analysis import (
    load_portfolio_thesis_holding_ids,
    matches_portfolio_snapshot,
    replace_portfolio_analysis_results,
)
from thesisguard_backend.portfolio_weights import refresh_current_weights
from thesisguard_backend.routers.holdings import OwnedHolding
from thesisguard_backend.schemas import (
    AlertResponse,
    AnalysisResultResponse,
    EvidenceHistoryGroupResponse,
    EvidenceResponse,
    HoldingAnalysisResponse,
    NaturalLanguageQueryEvidenceResponse,
    NaturalLanguageQueryRequest,
    NaturalLanguageQueryResponse,
    NaturalLanguageQueryScopeResponse,
    ThesisResponse,
    ThesisVersionResponse,
)

router = APIRouter(tags=["analysis"])

OwnedPortfolio = Annotated[orm.Portfolio, Depends(get_owned_portfolio)]

# Evidence at or above this impact is auto-saved to history at analysis time
# (both manual "재분석" and the scheduler's automatic run share this function),
# so the user no longer has to remember to click "주요 근거로 저장" for it.
_HISTORY_WORTHY_IMPACT = {EvidenceImpact.HIGH, EvidenceImpact.MEDIUM}


async def get_owned_evidence(
    evidence_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> orm.Evidence:
    evidence = await db.get(orm.Evidence, evidence_id)
    if evidence is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "근거를 찾을 수 없습니다.")
    thesis = await db.get(orm.Thesis, evidence.thesis_id)
    holding = await db.get(orm.Holding, thesis.holding_id) if thesis else None
    portfolio = await db.get(orm.Portfolio, holding.portfolio_id) if holding else None
    if portfolio is None or portfolio.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "근거를 찾을 수 없습니다.")
    return evidence


OwnedEvidence = Annotated[orm.Evidence, Depends(get_owned_evidence)]

# (previous_confidence, new_confidence, ticker, change_reason, evidence) ->
# AlertDecision. Lets callers other than the manual endpoint (e.g. the
# scheduler) swap in their own alert rule instead of C's LLM-judged
# result.alert_decision, while still having C's own explanation/evidence
# available to build a readable email body from.
AlertDecisionFactory = Callable[[int, int, str, str, list[EvidenceItem]], AlertDecision]


async def _load_scoped_evidence(
    db: AsyncSession, *, thesis_id, current_version_id
) -> list[EvidenceResponse]:
    rows = list(
        await db.scalars(
            select(orm.Evidence)
            .where(orm.Evidence.thesis_id == thesis_id)
            .order_by(orm.Evidence.created_at.asc())
        )
    )
    new_rows = [
        row
        for row in rows
        if row.thesis_version_id == current_version_id and not is_duplicate_placeholder(row)
    ]
    new_document_ids = {row.document_id for row in new_rows}
    past_rows = select_substantive_evidence(
        [row for row in rows if row.thesis_version_id != current_version_id],
        max_items=get_settings().evidence_history_max_items,
    )
    past_rows = [row for row in reversed(past_rows) if row.document_id not in new_document_ids]
    return [
        *(
            EvidenceResponse.model_validate(row).model_copy(update={"evidence_scope": "NEW"})
            for row in new_rows
        ),
        *(
            EvidenceResponse.model_validate(row).model_copy(update={"evidence_scope": "PAST"})
            for row in past_rows
        ),
    ]


@router.post("/api/holdings/{holding_id}/analyze", response_model=HoldingAnalysisResponse)
async def analyze_holding(
    holding: OwnedHolding, db: DbSession, current_user: CurrentUser
) -> HoldingAnalysisResponse:
    return await run_analysis_and_save(holding, db, current_user)


async def run_analysis_and_save(
    holding: orm.Holding,
    db: DbSession,
    current_user: orm.User,
    *,
    alert_decision_factory: AlertDecisionFactory | None = None,
    is_scheduled: bool = False,
) -> HoldingAnalysisResponse:
    thesis = await db.scalar(select(orm.Thesis).where(orm.Thesis.holding_id == holding.id))
    if thesis is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "이 종목에는 아직 등록된 투자 논리가 없습니다."
        )
    if not thesis.logic_graph:
        thesis.logic_graph = normalize_logic_graph(
            None,
            main_thesis=thesis.main_thesis,
            key_assumptions=thesis.key_assumptions,
        ).model_dump(mode="json")

    # Snapshot the thesis as it was BEFORE this analysis, shaped like the
    # frontend's Thesis interface (frontend/types/schema.ts) since
    # ThesisVersion.snapshot is typed as a full Thesis there. Built here —
    # before the weight-refresh commit and the agent workflow — because reading
    # thesis.updated_at after a flush triggers a lazy reload of that expired
    # onupdate column, which raises MissingGreenlet in this async session.
    pre_analysis_snapshot = {
        "id": str(thesis.id),
        "holding_id": str(thesis.holding_id),
        "raw_input": thesis.raw_input,
        "main_thesis": thesis.main_thesis,
        "key_assumptions": thesis.key_assumptions,
        "positive_signals": thesis.positive_signals,
        "negative_signals": thesis.negative_signals,
        "key_risks": thesis.key_risks,
        "logic_graph": thesis.logic_graph,
        "score_breakdown": thesis.score_breakdown,
        "confidence_score": thesis.confidence_score,
        "status": thesis.status.value if hasattr(thesis.status, "value") else thesis.status,
        "created_at": thesis.created_at.isoformat(),
        "updated_at": thesis.updated_at.isoformat(),
    }
    previous_confidence = thesis.confidence_score

    portfolio = await db.get(orm.Portfolio, holding.portfolio_id)
    portfolio_holdings = list(
        await db.scalars(select(orm.Holding).where(orm.Holding.portfolio_id == portfolio.id))
    )
    if await refresh_current_weights(portfolio_holdings, cash_ratio=portfolio.cash_ratio):
        await db.commit()

    with observe_llm_operation(
        "thesisguard.analyze-holding",
        user_id=str(current_user.id),
        session_id=f"portfolio:{portfolio.id}",
        input={
            "portfolio_id": str(portfolio.id),
            "holding_id": str(holding.id),
            "ticker": holding.ticker,
        },
        metadata={
            "portfolio_id": portfolio.id,
            "holding_id": holding.id,
            "ticker": holding.ticker,
        },
        tags=["holding-analysis", holding.ticker.lower()],
    ) as trace:
        # Rebuild the agent's WorkflowConfig from current AppSettings right
        # before running so an admin's scoring/policy/LLM parameter change
        # takes effect on this run without a redeploy (the graph is otherwise
        # compiled once at app startup — see agent_adapters.build_agent_from_settings).
        configure_agent(await build_agent_from_settings(session_factory, db))
        result = await arun_analysis_workflow(
            str(portfolio.id),
            str(holding.id),
            runnable_config=trace.runnable_config,
        )
        trace.set_output(result.model_dump(mode="json"))

    next_version_no = (
        await db.scalar(
            select(func.coalesce(func.max(orm.ThesisVersion.version_no), 0)).where(
                orm.ThesisVersion.thesis_id == thesis.id
            )
        )
    ) + 1

    thesis_version = orm.ThesisVersion(
        thesis_id=thesis.id,
        version_no=next_version_no,
        confidence_score=result.updated_confidence,
        status=result.updated_status,
        change_reason=result.change_reason,
        conflicting_assumptions=result.conflicting_assumptions,
        observation_points=result.observation_points,
        snapshot=pre_analysis_snapshot,
    )
    db.add(thesis_version)
    # thesis_version.id's default=uuid.uuid4 only applies at flush time, so
    # flush now — before it's read below — or every evidence row's
    # thesis_version_id ends up NULL.
    await db.flush()

    thesis.confidence_score = result.updated_confidence
    thesis.status = result.updated_status
    thesis.score_breakdown = result.score_breakdown.model_dump(mode="json")

    impacts_by_document = {
        item.document_id: item for item in result.score_breakdown.evidence_impacts
    }

    evidence_rows = [
        orm.Evidence(
            thesis_id=thesis.id,
            thesis_version_id=thesis_version.id,
            document_id=item.document_id,
            source_type=item.source_type,
            source_url=str(item.source_url) if item.source_url else None,
            vector_doc_id=item.vector_doc_id,
            content_snippet=item.content_snippet,
            classification=item.classification,
            impact=item.impact,
            reason=item.reason,
            related_assumptions=item.related_assumptions,
            assumption_findings=[
                finding.model_dump(mode="json") for finding in item.assumption_findings
            ],
            score_delta=(
                impacts_by_document[item.document_id].score_delta
                if item.document_id in impacts_by_document
                else 0
            ),
            node_contributions=(
                [
                    contribution.model_dump(mode="json")
                    for contribution in impacts_by_document[item.document_id].node_contributions
                ]
                if item.document_id in impacts_by_document
                else []
            ),
            published_at=item.published_at,
            saved_to_history=item.impact in _HISTORY_WORTHY_IMPACT,
        )
        for item in result.evidence
    ]
    db.add_all(evidence_rows)

    analysis_result = orm.AnalysisResult(
        thesis_id=thesis.id,
        thesis_version_id=thesis_version.id,
        analysis_type=orm.AnalysisType.BULL_BEAR_JUDGE,
        bull_summary=result.bull_summary,
        bear_summary=result.bear_summary,
        judge_summary=result.judge_summary,
        raw_result=result.model_dump(mode="json"),
    )
    db.add(analysis_result)

    portfolio_thesis_holding_ids = await load_portfolio_thesis_holding_ids(db, portfolio.id)
    await replace_portfolio_analysis_results(
        db,
        portfolio_id=portfolio.id,
        analysis=result.concentration,
        portfolio_holding_ids=portfolio_thesis_holding_ids,
    )

    await db.commit()
    await db.refresh(thesis)
    await db.refresh(thesis_version)
    await db.refresh(analysis_result)
    await refresh_evidence_history_file(db, holding=holding, thesis=thesis)

    decision = (
        alert_decision_factory(
            previous_confidence,
            result.updated_confidence,
            holding.ticker,
            result.change_reason,
            result.evidence,
        )
        if alert_decision_factory is not None
        else result.alert_decision
    )
    alert = await handle_alert_decision(
        db,
        user=current_user,
        portfolio=portfolio,
        thesis=thesis,
        ticker=holding.ticker,
        decision=decision,
        is_scheduled=is_scheduled,
    )

    return HoldingAnalysisResponse(
        thesis=ThesisResponse.model_validate(thesis),
        version=ThesisVersionResponse.model_validate(thesis_version),
        evidence=await _load_scoped_evidence(
            db, thesis_id=thesis.id, current_version_id=thesis_version.id
        ),
        analysis_result=AnalysisResultResponse.model_validate(analysis_result),
        alert=AlertResponse.model_validate(alert) if alert else None,
    )


@router.get("/api/holdings/{holding_id}/analysis", response_model=HoldingAnalysisResponse)
async def get_latest_analysis(holding: OwnedHolding, db: DbSession) -> HoldingAnalysisResponse:
    """The persisted counterpart of POST /analyze's response, so the frontend
    can restore the last analysis (evidence, bull/bear/judge, changes) after
    navigating away instead of losing it once the in-memory result is gone."""

    thesis = await db.scalar(select(orm.Thesis).where(orm.Thesis.holding_id == holding.id))
    if thesis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "이 종목에는 등록된 투자 논리가 없습니다.")

    thesis_version = await db.scalar(
        select(orm.ThesisVersion)
        .where(orm.ThesisVersion.thesis_id == thesis.id)
        .order_by(orm.ThesisVersion.version_no.desc())
        .limit(1)
    )
    if thesis_version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "이 종목은 아직 분석된 적이 없습니다.")

    analysis_result = await db.scalar(
        select(orm.AnalysisResult)
        .where(
            orm.AnalysisResult.thesis_id == thesis.id,
            orm.AnalysisResult.analysis_type == orm.AnalysisType.BULL_BEAR_JUDGE,
        )
        .order_by(orm.AnalysisResult.created_at.desc())
        .limit(1)
    )
    alert = await db.scalar(
        select(orm.Alert)
        .where(orm.Alert.thesis_id == thesis.id)
        .order_by(orm.Alert.created_at.desc())
        .limit(1)
    )

    return HoldingAnalysisResponse(
        thesis=ThesisResponse.model_validate(thesis),
        version=ThesisVersionResponse.model_validate(thesis_version),
        evidence=await _load_scoped_evidence(
            db, thesis_id=thesis.id, current_version_id=thesis_version.id
        ),
        analysis_result=AnalysisResultResponse.model_validate(analysis_result),
        alert=AlertResponse.model_validate(alert) if alert else None,
    )


@router.get(
    "/api/portfolios/{portfolio_id}/concentration", response_model=list[AnalysisResultResponse]
)
async def get_concentration(portfolio: OwnedPortfolio, db: DbSession) -> list[orm.AnalysisResult]:
    result = await db.scalars(
        select(orm.AnalysisResult)
        .where(
            orm.AnalysisResult.portfolio_id == portfolio.id,
            orm.AnalysisResult.analysis_type == orm.AnalysisType.THESIS_CONCENTRATION,
        )
        .order_by(orm.AnalysisResult.created_at.desc())
    )
    current_holding_ids = await load_portfolio_thesis_holding_ids(db, portfolio.id)
    return [row for row in result if matches_portfolio_snapshot(row, current_holding_ids)]


@router.get(
    "/api/portfolios/{portfolio_id}/common-risk",
    response_model=list[AnalysisResultResponse],
)
async def get_common_risk(portfolio: OwnedPortfolio, db: DbSession) -> list[orm.AnalysisResult]:
    result = await db.scalars(
        select(orm.AnalysisResult)
        .where(
            orm.AnalysisResult.portfolio_id == portfolio.id,
            orm.AnalysisResult.analysis_type == orm.AnalysisType.COMMON_RISK,
        )
        .order_by(orm.AnalysisResult.created_at.desc())
    )
    current_holding_ids = await load_portfolio_thesis_holding_ids(db, portfolio.id)
    return [row for row in result if matches_portfolio_snapshot(row, current_holding_ids)]


@router.get(
    "/api/portfolios/{portfolio_id}/evidence-history",
    response_model=list[EvidenceHistoryGroupResponse],
)
async def get_evidence_history(
    portfolio: OwnedPortfolio, db: DbSession
) -> list[EvidenceHistoryGroupResponse]:
    """One group per holding that has saved evidence, so the frontend can
    render a per-ticker view (tabs, accordion, a dedicated page — routing
    isn't decided yet) without needing a separate request per holding.
    Groups are ordered by their most recent saved evidence; entries within a
    group are newest first."""

    rows = (
        await db.execute(
            select(orm.Evidence, orm.Holding.id, orm.Holding.ticker)
            .join(orm.Thesis, orm.Thesis.id == orm.Evidence.thesis_id)
            .join(orm.Holding, orm.Holding.id == orm.Thesis.holding_id)
            .where(
                orm.Holding.portfolio_id == portfolio.id,
                orm.Evidence.saved_to_history.is_(True),
            )
            .order_by(orm.Evidence.created_at.desc())
        )
    ).all()

    groups: dict[uuid.UUID, EvidenceHistoryGroupResponse] = {}
    for evidence, holding_id, ticker in rows:
        group = groups.get(holding_id)
        if group is None:
            group = EvidenceHistoryGroupResponse(holding_id=holding_id, ticker=ticker, entries=[])
            groups[holding_id] = group
        group.entries.append(EvidenceResponse.model_validate(evidence))
    return list(groups.values())


@router.get(
    "/api/holdings/{holding_id}/evidence-history",
    response_model=list[EvidenceResponse],
)
async def get_holding_evidence_history(holding: OwnedHolding, db: DbSession) -> list[orm.Evidence]:
    """Saved-history evidence scoped to a single holding, for whenever the
    frontend lands on per-ticker routing instead of (or alongside) the
    portfolio-wide grouped endpoint above."""

    thesis_id = await db.scalar(select(orm.Thesis.id).where(orm.Thesis.holding_id == holding.id))
    if thesis_id is None:
        return []
    result = await db.scalars(
        select(orm.Evidence)
        .where(orm.Evidence.thesis_id == thesis_id, orm.Evidence.saved_to_history.is_(True))
        .order_by(orm.Evidence.created_at.desc())
    )
    return list(result)


@router.post("/api/evidence/{evidence_id}/save", response_model=EvidenceResponse)
async def save_evidence(evidence: OwnedEvidence, db: DbSession) -> orm.Evidence:
    evidence.saved_to_history = True
    await db.commit()
    await db.refresh(evidence)
    return evidence


@router.delete("/api/evidence/{evidence_id}/save", status_code=status.HTTP_204_NO_CONTENT)
async def unsave_evidence(evidence: OwnedEvidence, db: DbSession) -> None:
    evidence.saved_to_history = False
    await db.commit()


@router.post("/api/portfolios/{portfolio_id}/query", response_model=NaturalLanguageQueryResponse)
async def query_portfolio(
    payload: NaturalLanguageQueryRequest, portfolio: OwnedPortfolio, db: DbSession, agent: Agent
) -> NaturalLanguageQueryResponse:
    """PRD 5.14 — natural-language portfolio Q&A.

    NOTE: evidence is picked by recency only (latest 50 rows across the
    portfolio's theses), not by semantic relevance to the question — there is
    no Vector Store wired up yet (ADR-0002 is still unresolved). Once one
    exists, replace this with a similarity search over `question`.
    """

    holding_count = len(
        list(
            await db.scalars(select(orm.Holding.id).where(orm.Holding.portfolio_id == portfolio.id))
        )
    )
    thesis_rows = list(
        await db.execute(
            select(orm.Thesis.id, orm.Holding.id, orm.Holding.ticker)
            .join(orm.Holding, orm.Holding.id == orm.Thesis.holding_id)
            .where(orm.Holding.portfolio_id == portfolio.id)
        )
    )
    thesis_ids = [row[0] for row in thesis_rows]
    # thesis_id -> (holding_id, ticker), so evidence rows (which only carry a
    # thesis_id) can be traced back to the holding they belong to.
    holding_by_thesis = {row[0]: (row[1], row[2]) for row in thesis_rows}

    evidence_limit = await settings_service.aget_setting(db, "qa.evidence_limit")
    evidence_rows = list(
        await db.scalars(
            select(orm.Evidence)
            .where(orm.Evidence.thesis_id.in_(thesis_ids))
            .order_by(orm.Evidence.created_at.desc())
            .limit(evidence_limit)
        )
    )
    evidence = [
        EvidenceItem(
            document_id=row.document_id,
            source_type=row.source_type,
            source_url=row.source_url,
            vector_doc_id=row.vector_doc_id,
            content_snippet=row.content_snippet,
            classification=row.classification,
            impact=row.impact,
            reason=row.reason,
            related_assumptions=row.related_assumptions,
            assumption_findings=row.assumption_findings,
            published_at=row.published_at,
        )
        for row in evidence_rows
    ]

    with observe_llm_operation(
        "thesisguard.portfolio-query",
        user_id=str(portfolio.user_id),
        session_id=f"portfolio:{portfolio.id}",
        input={"portfolio_id": str(portfolio.id), "question": payload.question},
        metadata={
            "portfolio_id": portfolio.id,
            "holding_count": holding_count,
            "thesis_count": len(thesis_ids),
            "candidate_evidence_count": len(evidence),
            "question_length": len(payload.question),
            "search_method": "RECENCY",
        },
        tags=["portfolio-query"],
    ) as trace:
        answer = await agent.aanswer_portfolio_query(
            str(portfolio.id),
            payload.question,
            evidence,
            runnable_config=trace.runnable_config,
        )
        trace.set_output(answer.model_dump(mode="json"))

    # The agent already filters evidence_document_ids down to IDs it was
    # actually shown (agents/model.py), but dedupe defensively here too so a
    # repeated ID can't produce two evidence cards on the frontend.
    evidence_by_document_id = {row.document_id: row for row in evidence_rows}
    seen_document_ids: set[str] = set()
    detailed_evidence: list[NaturalLanguageQueryEvidenceResponse] = []
    for document_id in answer.evidence_document_ids:
        if document_id in seen_document_ids:
            continue
        row = evidence_by_document_id.get(document_id)
        if row is None:
            continue
        holding_id, ticker = holding_by_thesis.get(row.thesis_id, (None, None))
        if holding_id is None:
            continue
        seen_document_ids.add(document_id)
        detailed_evidence.append(
            NaturalLanguageQueryEvidenceResponse(
                document_id=row.document_id,
                holding_id=holding_id,
                ticker=ticker,
                content_snippet=row.content_snippet,
                source_url=row.source_url,
                published_at=row.published_at,
                classification=row.classification,
                impact=row.impact,
                related_assumptions=row.related_assumptions,
            )
        )

    limitations = list(answer.limitations)
    if holding_count > len(thesis_ids):
        limitations.append(
            "아직 투자 논리(Thesis)가 등록되지 않은 종목은 이번 답변에 반영되지 않았습니다."
        )
    if not evidence_rows:
        limitations.append("포트폴리오에 저장된 근거가 아직 없습니다.")
    else:
        theses_with_evidence = {row.thesis_id for row in evidence_rows}
        if len(theses_with_evidence) < len(thesis_ids):
            limitations.append("일부 종목은 근거가 없어 이번 답변에 반영되지 않았을 수 있습니다.")
        if len(evidence_rows) >= evidence_limit:
            limitations.append(f"최근 저장된 근거 중 최신 {evidence_limit}건만 검토했습니다.")
        limitations.append("근거는 질문과의 의미적 관련성이 아니라 최신순으로만 선택했습니다.")
        if any(item.source_url is None for item in detailed_evidence):
            limitations.append("일부 근거는 원문 링크가 없습니다.")

    latest_evidence_at = max(
        (row.published_at for row in evidence_rows if row.published_at is not None),
        default=None,
    )

    response = NaturalLanguageQueryResponse(
        answer=answer.answer,
        evidence_document_ids=answer.evidence_document_ids,
        evidence=detailed_evidence,
        limitations=limitations,
        scope=NaturalLanguageQueryScopeResponse(
            holding_count=holding_count,
            thesis_count=len(thesis_ids),
            candidate_evidence_count=len(evidence_rows),
            selected_evidence_count=len(detailed_evidence),
            latest_evidence_at=latest_evidence_at,
        ),
    )

    # Every Q&A pair is logged for the admin console (training-data export),
    # per PBL mentoring feedback — see docs/PORTFOLIO_QA_BACKEND_TASKS.md.
    db.add(
        orm.QaLog(
            user_id=portfolio.user_id,
            portfolio_id=portfolio.id,
            question=payload.question,
            answer=answer.answer,
            evidence_document_ids=list(answer.evidence_document_ids),
        )
    )
    await db.commit()

    return response
