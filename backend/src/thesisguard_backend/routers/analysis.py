"""POST /api/holdings/{id}/analyze — the B<->C integration point.

Calls C's ``arun_analysis_workflow()``, persists every part of
``ThesisAnalysisResult`` across theses/thesis_versions/evidence/
analysis_results/alerts, and returns the same result to the caller.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from agents.graph import arun_analysis_workflow
from agents.models import EvidenceItem
from thesisguard_backend import models as orm
from thesisguard_backend.alert_engine import handle_alert_decision
from thesisguard_backend.deps import Agent, CurrentUser, DbSession, get_owned_portfolio
from thesisguard_backend.routers.holdings import OwnedHolding
from thesisguard_backend.schemas import (
    AlertDecisionResponse,
    AnalysisResultResponse,
    AnalyzeResponse,
    CommonRiskResponse,
    ConcentrationThemeResponse,
    EvidenceResponse,
    NaturalLanguageQueryRequest,
    NaturalLanguageQueryResponse,
    ThesisResponse,
    ThesisVersionResponse,
)

router = APIRouter(tags=["analysis"])

OwnedPortfolio = Annotated[orm.Portfolio, Depends(get_owned_portfolio)]


@router.post("/api/holdings/{holding_id}/analyze", response_model=AnalyzeResponse)
async def analyze_holding(
    holding: OwnedHolding, db: DbSession, current_user: CurrentUser
) -> AnalyzeResponse:
    thesis = await db.scalar(select(orm.Thesis).where(orm.Thesis.holding_id == holding.id))
    if thesis is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "이 종목에는 아직 등록된 투자 논리가 없습니다."
        )
    portfolio = await db.get(orm.Portfolio, holding.portfolio_id)

    result = await arun_analysis_workflow(str(portfolio.id), str(holding.id))

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
        snapshot={
            "main_thesis": thesis.main_thesis,
            "key_assumptions": thesis.key_assumptions,
            "positive_signals": thesis.positive_signals,
            "negative_signals": thesis.negative_signals,
            "key_risks": thesis.key_risks,
            "confidence_score": thesis.confidence_score,
            "status": thesis.status.value if hasattr(thesis.status, "value") else thesis.status,
        },
    )
    db.add(thesis_version)

    thesis.confidence_score = result.updated_confidence
    thesis.status = result.updated_status

    evidence_rows = [
        orm.Evidence(
            thesis_id=thesis.id,
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

    db.add(
        orm.AnalysisResult(
            thesis_id=thesis.id,
            analysis_type=orm.AnalysisType.BULL_BEAR_JUDGE,
            bull_summary=result.bull_summary,
            bear_summary=result.bear_summary,
            judge_summary=result.judge_summary,
            raw_result=result.model_dump(mode="json"),
        )
    )

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

    await handle_alert_decision(
        db,
        user=current_user,
        portfolio=portfolio,
        thesis=thesis,
        ticker=holding.ticker,
        decision=result.alert_decision,
    )

    return AnalyzeResponse(
        thesis=ThesisResponse.model_validate(thesis),
        thesis_version=ThesisVersionResponse.model_validate(thesis_version),
        evidence=[EvidenceResponse.model_validate(row) for row in evidence_rows],
        bull_summary=result.bull_summary,
        bear_summary=result.bear_summary,
        judge_summary=result.judge_summary,
        concentration_themes=[
            ConcentrationThemeResponse(
                theme=t.theme,
                concentration_score=t.concentration_score,
                affected_holdings=t.affected_holdings,
                shared_assumptions=t.shared_assumptions,
            )
            for t in result.concentration.themes
        ],
        common_risks=[
            CommonRiskResponse(
                risk=r.risk,
                affected_holdings=r.affected_holdings,
                evidence_document_ids=r.evidence_document_ids,
            )
            for r in result.concentration.common_risks
        ],
        alert=AlertDecisionResponse(
            severity=result.alert_decision.severity,
            should_send=result.alert_decision.should_send,
            delivery=result.alert_decision.delivery,
            reason=result.alert_decision.reason,
        ),
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


@router.get("/api/portfolios/{portfolio_id}/common-risk", response_model=list[AnalysisResultResponse])
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

    answer = await agent.aanswer_portfolio_query(str(portfolio.id), payload.question, evidence)
    return NaturalLanguageQueryResponse(
        answer=answer.answer,
        evidence_document_ids=answer.evidence_document_ids,
        limitations=answer.limitations,
    )
