"""POST /api/holdings/{id}/analyze — the B<->C integration point.

Calls C's ``arun_analysis_workflow()``, persists every part of
``ThesisAnalysisResult`` across theses/thesis_versions/evidence/
analysis_results/alerts, and returns the same result to the caller.
"""

from __future__ import annotations

from typing import Annotated

from agents.graph import arun_analysis_workflow
from agents.models import EvidenceItem
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from thesisguard_backend import models as orm
from thesisguard_backend.alert_engine import handle_alert_decision
from thesisguard_backend.deps import Agent, CurrentUser, DbSession, get_owned_portfolio
from thesisguard_backend.observability import observe_llm_operation
from thesisguard_backend.routers.holdings import OwnedHolding
from thesisguard_backend.schemas import (
    AlertResponse,
    AnalysisResultResponse,
    EvidenceResponse,
    HoldingAnalysisResponse,
    NaturalLanguageQueryRequest,
    NaturalLanguageQueryResponse,
    ThesisResponse,
    ThesisVersionResponse,
)

router = APIRouter(tags=["analysis"])

OwnedPortfolio = Annotated[orm.Portfolio, Depends(get_owned_portfolio)]


@router.post("/api/holdings/{holding_id}/analyze", response_model=HoldingAnalysisResponse)
async def analyze_holding(
    holding: OwnedHolding, db: DbSession, current_user: CurrentUser
) -> HoldingAnalysisResponse:
    thesis = await db.scalar(select(orm.Thesis).where(orm.Thesis.holding_id == holding.id))
    if thesis is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "이 종목에는 아직 등록된 투자 논리가 없습니다."
        )
    portfolio = await db.get(orm.Portfolio, holding.portfolio_id)

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

    # Snapshot the thesis as it was BEFORE this analysis, shaped like the
    # frontend's Thesis interface (frontend/types/schema.ts) since
    # ThesisVersion.snapshot is typed as a full Thesis there.
    pre_analysis_snapshot = {
        "id": str(thesis.id),
        "holding_id": str(thesis.holding_id),
        "raw_input": thesis.raw_input,
        "main_thesis": thesis.main_thesis,
        "key_assumptions": thesis.key_assumptions,
        "positive_signals": thesis.positive_signals,
        "negative_signals": thesis.negative_signals,
        "key_risks": thesis.key_risks,
        "confidence_score": thesis.confidence_score,
        "status": thesis.status.value if hasattr(thesis.status, "value") else thesis.status,
        "created_at": thesis.created_at.isoformat(),
        "updated_at": thesis.updated_at.isoformat(),
    }
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
            published_at=item.published_at,
        )
        for item in result.evidence
    ]
    db.add_all(evidence_rows)

    analysis_result = orm.AnalysisResult(
        thesis_id=thesis.id,
        analysis_type=orm.AnalysisType.BULL_BEAR_JUDGE,
        bull_summary=result.bull_summary,
        bear_summary=result.bear_summary,
        judge_summary=result.judge_summary,
        raw_result=result.model_dump(mode="json"),
    )
    db.add(analysis_result)

    for theme in result.concentration.themes:
        db.add(
            orm.AnalysisResult(
                portfolio_id=portfolio.id,
                analysis_type=orm.AnalysisType.THESIS_CONCENTRATION,
                concentration_theme=theme.theme,
                concentration_score=theme.concentration_score,
                affected_holdings=theme.affected_holdings,
                raw_result=theme.model_dump(mode="json"),
            )
        )

    for risk in result.concentration.common_risks:
        # CommonRisk has no numeric score, so concentration_theme/-score are
        # reused as a generic label/[unset] pair rather than adding new columns.
        db.add(
            orm.AnalysisResult(
                portfolio_id=portfolio.id,
                analysis_type=orm.AnalysisType.COMMON_RISK,
                concentration_theme=risk.risk,
                affected_holdings=risk.affected_holdings,
                raw_result=risk.model_dump(mode="json"),
            )
        )

    await db.commit()
    await db.refresh(thesis)
    await db.refresh(thesis_version)
    await db.refresh(analysis_result)

    alert = await handle_alert_decision(
        db,
        user=current_user,
        portfolio=portfolio,
        thesis=thesis,
        ticker=holding.ticker,
        decision=result.alert_decision,
    )

    return HoldingAnalysisResponse(
        thesis=ThesisResponse.model_validate(thesis),
        version=ThesisVersionResponse.model_validate(thesis_version),
        evidence=[EvidenceResponse.model_validate(row) for row in evidence_rows],
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
    evidence_rows = list(
        await db.scalars(
            select(orm.Evidence).where(orm.Evidence.thesis_version_id == thesis_version.id)
        )
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
        evidence=[EvidenceResponse.model_validate(row) for row in evidence_rows],
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
    return list(result)


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
    return list(result)


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

    thesis_ids = list(
        await db.scalars(
            select(orm.Thesis.id)
            .join(orm.Holding, orm.Holding.id == orm.Thesis.holding_id)
            .where(orm.Holding.portfolio_id == portfolio.id)
        )
    )
    evidence_rows = list(
        await db.scalars(
            select(orm.Evidence)
            .where(orm.Evidence.thesis_id.in_(thesis_ids))
            .order_by(orm.Evidence.created_at.desc())
            .limit(50)
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
            published_at=row.published_at,
        )
        for row in evidence_rows
    ]

    with observe_llm_operation(
        "thesisguard.portfolio-query",
        user_id=str(portfolio.user_id),
        session_id=f"portfolio:{portfolio.id}",
        input={"portfolio_id": str(portfolio.id), "question": payload.question},
        metadata={"portfolio_id": portfolio.id, "evidence_count": len(evidence)},
        tags=["portfolio-query"],
    ) as trace:
        answer = await agent.aanswer_portfolio_query(
            str(portfolio.id),
            payload.question,
            evidence,
            runnable_config=trace.runnable_config,
        )
        trace.set_output(answer.model_dump(mode="json"))
    return NaturalLanguageQueryResponse(
        answer=answer.answer,
        evidence_document_ids=answer.evidence_document_ids,
        limitations=answer.limitations,
    )
