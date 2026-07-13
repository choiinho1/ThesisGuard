"""Portfolio CRUD + dashboard aggregation."""

from __future__ import annotations

import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from thesisguard_backend import models as orm
from thesisguard_backend.agent_adapters import get_market_snapshot
from thesisguard_backend.deps import CurrentUser, DbSession, get_owned_portfolio
from thesisguard_backend.schemas import (
    PortfolioCreateRequest,
    PortfolioDashboardResponse,
    PortfolioResponse,
    PortfolioUpdateRequest,
    ThemeDependency,
    ThesisStatusCard,
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
    holdings = list(
        await db.scalars(
            select(orm.Holding)
            .where(orm.Holding.portfolio_id == portfolio_id)
            .options(selectinload(orm.Holding.thesis).selectinload(orm.Thesis.versions))
        )
    )

    snapshots = await asyncio.gather(
        *(get_market_snapshot(holding.ticker) for holding in holdings), return_exceptions=True
    )

    total_value = 0.0
    total_cost = 0.0
    allocation: dict[str, float] = {}
    thesis_status: list[ThesisStatusCard] = []
    for holding, snapshot in zip(holdings, snapshots, strict=False):
        price = holding.avg_buy_price
        if not isinstance(snapshot, Exception) and snapshot.latest is not None:
            price = snapshot.latest.close
        market_value = holding.quantity * price
        total_value += market_value
        total_cost += holding.quantity * holding.avg_buy_price
        allocation[holding.ticker] = market_value

        if holding.thesis is not None:
            versions = holding.thesis.versions
            previous_confidence = versions[-2].confidence_score if len(versions) >= 2 else None
            thesis_status.append(
                ThesisStatusCard(
                    holding_id=holding.id,
                    ticker=holding.ticker,
                    confidence_score=holding.thesis.confidence_score,
                    previous_confidence_score=previous_confidence,
                    status=holding.thesis.status,
                )
            )

    if total_value > 0:
        allocation = {ticker: round(value / total_value * 100, 2) for ticker, value in allocation.items()}
        for holding in holdings:
            holding.current_weight = allocation.get(holding.ticker, 0.0)
        await db.commit()
    total_return_pct = round((total_value - total_cost) / total_cost * 100, 2) if total_cost > 0 else 0.0

    recent_versions = list(
        await db.scalars(
            select(orm.ThesisVersion)
            .join(orm.Thesis, orm.Thesis.id == orm.ThesisVersion.thesis_id)
            .join(orm.Holding, orm.Holding.id == orm.Thesis.holding_id)
            .where(orm.Holding.portfolio_id == portfolio_id)
            .order_by(orm.ThesisVersion.created_at.desc())
            .limit(5)
        )
    )

    concentration_rows = list(
        await db.scalars(
            select(orm.AnalysisResult)
            .where(
                orm.AnalysisResult.portfolio_id == portfolio_id,
                orm.AnalysisResult.analysis_type == orm.AnalysisType.THESIS_CONCENTRATION,
            )
            .order_by(orm.AnalysisResult.created_at.desc())
            .limit(5)
        )
    )

    return PortfolioDashboardResponse(
        portfolio=PortfolioResponse.model_validate(portfolio),
        total_value=round(total_value, 2),
        total_return_pct=total_return_pct,
        cash_ratio=portfolio.cash_ratio,
        allocation=allocation,
        thesis_status=thesis_status,
        recent_changes=[ThesisVersionResponse.model_validate(v) for v in recent_versions],
        theme_dependency=[
            ThemeDependency(
                theme=row.concentration_theme or "",
                concentration_score=row.concentration_score or 0.0,
                affected_holdings=row.affected_holdings,
            )
            for row in concentration_rows
        ],
    )
