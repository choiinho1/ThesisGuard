"""Portfolio CRUD + dashboard aggregation."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from thesisguard_backend import models as orm
from thesisguard_backend.deps import CurrentUser, DbSession, get_owned_portfolio
from thesisguard_backend.portfolio_analysis import matches_portfolio_snapshot
from thesisguard_backend.portfolio_weights import refresh_current_weights
from thesisguard_backend.schemas import (
    AlertResponse,
    AnalysisResultResponse,
    DashboardHoldingResponse,
    PortfolioCreateRequest,
    PortfolioDashboardResponse,
    PortfolioResponse,
    PortfolioUpdateRequest,
    ThesisVersionResponse,
)

router = APIRouter(prefix="/api/portfolios", tags=["portfolios"])

OwnedPortfolio = Annotated[orm.Portfolio, Depends(get_owned_portfolio)]


@router.get("", response_model=list[PortfolioResponse])
async def list_portfolios(db: DbSession, current_user: CurrentUser) -> list[orm.Portfolio]:
    result = await db.scalars(select(orm.Portfolio).where(orm.Portfolio.user_id == current_user.id))
    return list(result)


@router.post("", response_model=PortfolioResponse, status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    payload: PortfolioCreateRequest, db: DbSession, current_user: CurrentUser
) -> orm.Portfolio:
    portfolio = orm.Portfolio(user_id=current_user.id, **payload.model_dump())
    db.add(portfolio)
    await db.commit()
    await db.refresh(portfolio)
    return portfolio


@router.get("/{portfolio_id}", response_model=PortfolioResponse)
async def get_portfolio(portfolio: OwnedPortfolio) -> orm.Portfolio:
    return portfolio


@router.put("/{portfolio_id}", response_model=PortfolioResponse)
async def update_portfolio(
    payload: PortfolioUpdateRequest, portfolio: OwnedPortfolio, db: DbSession
) -> orm.Portfolio:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(portfolio, field, value)
    await db.commit()
    await db.refresh(portfolio)
    return portfolio


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portfolio(portfolio: OwnedPortfolio, db: DbSession) -> None:
    await db.delete(portfolio)
    await db.commit()


@router.get("/{portfolio_id}/dashboard", response_model=PortfolioDashboardResponse)
async def get_dashboard(
    portfolio_id: uuid.UUID, portfolio: OwnedPortfolio, db: DbSession
) -> PortfolioDashboardResponse:
    """Return the dashboard with current market-value portfolio weights."""

    holdings_query = (
        select(orm.Holding)
        .where(orm.Holding.portfolio_id == portfolio_id)
        .options(selectinload(orm.Holding.thesis).selectinload(orm.Thesis.versions))
        .order_by(orm.Holding.created_at)
    )
    holdings = list(await db.scalars(holdings_query))
    weights_changed = await refresh_current_weights(
        holdings,
        cash_ratio=portfolio.cash_ratio,
    )
    if weights_changed:
        await db.commit()
        # Updating current_weight also applies Holding.updated_at's SQL-side
        # on-update expression. SQLAlchemy expires that generated value even
        # with expire_on_commit=False, so serializing the pre-commit objects can
        # trigger an async lazy load and raise MissingGreenlet. Reload the rows
        # explicitly before Pydantic accesses them.
        holdings = list(await db.scalars(holdings_query.execution_options(populate_existing=True)))

    holding_responses = []
    for holding in holdings:
        dashboard_holding = DashboardHoldingResponse.model_validate(holding)
        if holding.thesis and holding.thesis.versions:
            dashboard_holding.latest_change = ThesisVersionResponse.model_validate(
                holding.thesis.versions[-1]
            )
        holding_responses.append(dashboard_holding)

    current_thesis_holding_ids = {
        str(holding.id) for holding in holdings if holding.thesis is not None
    }
    concentration_candidates = list(
        await db.scalars(
            select(orm.AnalysisResult)
            .where(
                orm.AnalysisResult.portfolio_id == portfolio_id,
                orm.AnalysisResult.analysis_type == orm.AnalysisType.THESIS_CONCENTRATION,
            )
            .order_by(
                orm.AnalysisResult.created_at.desc(),
                orm.AnalysisResult.concentration_score.desc(),
            )
        )
    )
    concentration = next(
        (
            row
            for row in concentration_candidates
            if matches_portfolio_snapshot(row, current_thesis_holding_ids)
        ),
        None,
    )
    common_risk_candidates = list(
        await db.scalars(
            select(orm.AnalysisResult)
            .where(
                orm.AnalysisResult.portfolio_id == portfolio_id,
                orm.AnalysisResult.analysis_type == orm.AnalysisType.COMMON_RISK,
            )
            .order_by(orm.AnalysisResult.created_at.desc())
        )
    )
    common_risks = [
        row
        for row in common_risk_candidates
        if matches_portfolio_snapshot(row, current_thesis_holding_ids)
    ][:10]
    recent_alerts = list(
        await db.scalars(
            select(orm.Alert)
            .where(orm.Alert.portfolio_id == portfolio_id)
            .order_by(orm.Alert.created_at.desc())
            .limit(10)
        )
    )

    concentration_response = None
    if concentration is not None:
        weight_by_holding_id = {str(holding.id): holding.current_weight for holding in holdings}
        current_score = min(
            100,
            sum(
                weight_by_holding_id.get(holding_id, 0)
                for holding_id in concentration.affected_holdings
            ),
        )
        concentration_response = AnalysisResultResponse.model_validate(concentration).model_copy(
            update={"concentration_score": round(current_score, 2)}
        )

    return PortfolioDashboardResponse(
        portfolio=PortfolioResponse.model_validate(portfolio),
        holdings=holding_responses,
        concentration=concentration_response,
        common_risks=[AnalysisResultResponse.model_validate(row) for row in common_risks],
        recent_alerts=[AlertResponse.model_validate(row) for row in recent_alerts],
    )
