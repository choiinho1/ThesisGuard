"""Persistence and freshness checks for portfolio-wide analysis results."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from agents.models import PortfolioAnalysis
from agents.portfolio_validation import is_absence_label
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from thesisguard_backend import models as orm

_PORTFOLIO_ANALYSIS_TYPES = (
    orm.AnalysisType.THESIS_CONCENTRATION,
    orm.AnalysisType.COMMON_RISK,
)


async def load_portfolio_thesis_holding_ids(
    db: AsyncSession,
    portfolio_id: uuid.UUID,
) -> set[str]:
    holding_ids = await db.scalars(
        select(orm.Holding.id)
        .join(orm.Thesis, orm.Thesis.holding_id == orm.Holding.id)
        .where(orm.Holding.portfolio_id == portfolio_id)
    )
    return {str(holding_id) for holding_id in holding_ids}


def matches_portfolio_snapshot(
    result: orm.AnalysisResult,
    current_holding_ids: set[str],
) -> bool:
    """Reject legacy or stale results generated for a different holding set."""

    raw_result = result.raw_result if isinstance(result.raw_result, dict) else {}
    snapshot = raw_result.get("portfolio_holding_ids")
    snapshot_matches = (
        isinstance(snapshot, list)
        and all(isinstance(item, str) for item in snapshot)
        and set(snapshot) == current_holding_ids
    )
    affected_holdings = result.affected_holdings
    affected_are_valid = (
        isinstance(affected_holdings, list)
        and len(set(affected_holdings)) >= 2
        and set(affected_holdings).issubset(current_holding_ids)
    )
    if not snapshot_matches or not affected_are_valid or not result.concentration_theme:
        return False
    if is_absence_label(result.concentration_theme):
        return False
    if result.analysis_type == orm.AnalysisType.THESIS_CONCENTRATION:
        shared_assumptions = raw_result.get("shared_assumptions")
        return isinstance(shared_assumptions, list) and any(
            isinstance(item, str) and item.strip() for item in shared_assumptions
        )
    return result.analysis_type == orm.AnalysisType.COMMON_RISK


async def replace_portfolio_analysis_results(
    db: AsyncSession,
    *,
    portfolio_id: uuid.UUID,
    analysis: PortfolioAnalysis,
    portfolio_holding_ids: Iterable[str],
) -> None:
    """Replace the current portfolio view so an empty result clears stale findings."""

    snapshot = sorted(set(portfolio_holding_ids))
    await db.execute(
        delete(orm.AnalysisResult).where(
            orm.AnalysisResult.portfolio_id == portfolio_id,
            orm.AnalysisResult.analysis_type.in_(_PORTFOLIO_ANALYSIS_TYPES),
        )
    )

    for theme in analysis.themes:
        raw_result = theme.model_dump(mode="json")
        raw_result["portfolio_holding_ids"] = snapshot
        db.add(
            orm.AnalysisResult(
                portfolio_id=portfolio_id,
                analysis_type=orm.AnalysisType.THESIS_CONCENTRATION,
                judge_summary=analysis.summary,
                concentration_theme=theme.theme,
                concentration_score=theme.concentration_score,
                affected_holdings=theme.affected_holdings,
                raw_result=raw_result,
            )
        )

    for risk in analysis.common_risks:
        raw_result = risk.model_dump(mode="json")
        raw_result["portfolio_holding_ids"] = snapshot
        db.add(
            orm.AnalysisResult(
                portfolio_id=portfolio_id,
                analysis_type=orm.AnalysisType.COMMON_RISK,
                concentration_theme=risk.risk,
                affected_holdings=risk.affected_holdings,
                raw_result=raw_result,
            )
        )
