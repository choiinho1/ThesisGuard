"""Portfolio CRUD + dashboard aggregation."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from thesisguard_backend import models as orm
from thesisguard_backend.deps import CurrentUser, DbSession, get_owned_portfolio
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
    result = await db.scalars(
        select(orm.Portfolio).where(orm.Portfolio.user_id == current_user.id)
    )
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
    """Mirrors frontend/types/schema.ts's PortfolioDashboard exactly: the
    frontend computes allocation/return figures client-side from holdings,
    so this endpoint returns raw rows rather than server-computed aggregates."""

    holdings = list(
        await db.scalars(
            select(orm.Holding)
            .where(orm.Holding.portfolio_id == portfolio_id)
            .options(selectinload(orm.Holding.thesis).selectinload(orm.Thesis.versions))
            .order_by(orm.Holding.created_at)
        )
    )
    holding_responses = []
    for holding in holdings:
        dashboard_holding = DashboardHoldingResponse.model_validate(holding)
        if holding.thesis and holding.thesis.versions:
            dashboard_holding.latest_change = ThesisVersionResponse.model_validate(
                holding.thesis.versions[-1]
            )
        holding_responses.append(dashboard_holding)

    concentration = await db.scalar(
        select(orm.AnalysisResult)
        .where(
            orm.AnalysisResult.portfolio_id == portfolio_id,
            orm.AnalysisResult.analysis_type == orm.AnalysisType.THESIS_CONCENTRATION,
        )
        .order_by(orm.AnalysisResult.created_at.desc())
        .limit(1)
    )
    common_risks = list(
        await db.scalars(
            select(orm.AnalysisResult)
            .where(
                orm.AnalysisResult.portfolio_id == portfolio_id,
                orm.AnalysisResult.analysis_type == orm.AnalysisType.COMMON_RISK,
            )
            .order_by(orm.AnalysisResult.created_at.desc())
            .limit(10)
        )
    )
    recent_alerts = list(
        await db.scalars(
            select(orm.Alert)
            .where(orm.Alert.portfolio_id == portfolio_id)
            .order_by(orm.Alert.created_at.desc())
            .limit(10)
        )
    )

    return PortfolioDashboardResponse(
        portfolio=PortfolioResponse.model_validate(portfolio),
        holdings=holding_responses,
        concentration=(
            AnalysisResultResponse.model_validate(concentration) if concentration else None
        ),
        common_risks=[AnalysisResultResponse.model_validate(row) for row in common_risks],
        recent_alerts=[AlertResponse.model_validate(row) for row in recent_alerts],
    )
