"""Holding CRUD + rebalancing (records a transaction snapshot, per TDD 5.3)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from thesisguard_backend import models as orm
from thesisguard_backend.deps import CurrentUser, DbSession, get_owned_portfolio
from thesisguard_backend.schemas import (
    HoldingCreateRequest,
    HoldingResponse,
    HoldingUpdateRequest,
    RebalanceRequest,
    TransactionResponse,
)

router = APIRouter(tags=["holdings"])

OwnedPortfolio = Annotated[orm.Portfolio, Depends(get_owned_portfolio)]


async def get_owned_holding(
    holding_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> orm.Holding:
    """Standalone /api/holdings/{holding_id} routes have no portfolio_id in the
    path, so ownership is checked by joining through the holding's portfolio."""

    holding = await db.get(orm.Holding, holding_id)
    if holding is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "종목을 찾을 수 없습니다.")
    portfolio = await db.get(orm.Portfolio, holding.portfolio_id)
    if portfolio is None or portfolio.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "종목을 찾을 수 없습니다.")
    return holding


OwnedHolding = Annotated[orm.Holding, Depends(get_owned_holding)]


@router.post(
    "/api/portfolios/{portfolio_id}/holdings",
    response_model=HoldingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_holding(
    payload: HoldingCreateRequest, portfolio: OwnedPortfolio, db: DbSession
) -> orm.Holding:
    existing_holding_id = await db.scalar(
        select(orm.Holding.id).where(
            orm.Holding.portfolio_id == portfolio.id,
            func.upper(func.trim(orm.Holding.ticker)) == payload.ticker,
        )
    )
    if existing_holding_id is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{payload.ticker}는 이미 이 포트폴리오에 등록되어 있습니다.",
        )

    holding = orm.Holding(portfolio_id=portfolio.id, **payload.model_dump())
    db.add(holding)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{payload.ticker}는 이미 이 포트폴리오에 등록되어 있습니다.",
        ) from None
    await db.refresh(holding)
    return holding


@router.put("/api/holdings/{holding_id}", response_model=HoldingResponse)
async def update_holding(
    payload: HoldingUpdateRequest, holding: OwnedHolding, db: DbSession
) -> orm.Holding:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(holding, field, value)
    await db.commit()
    await db.refresh(holding)
    return holding


@router.delete("/api/holdings/{holding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_holding(holding: OwnedHolding, db: DbSession) -> None:
    await db.delete(holding)
    await db.commit()


@router.post(
    "/api/portfolios/{portfolio_id}/rebalance",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def rebalance_portfolio(
    payload: RebalanceRequest, portfolio: OwnedPortfolio, db: DbSession
) -> orm.Transaction:
    holdings_by_id = {h.id: h for h in portfolio.holdings}
    before_snapshot = {
        str(h.id): {"ticker": h.ticker, "quantity": h.quantity, "target_weight": h.target_weight}
        for h in portfolio.holdings
    }

    for item in payload.holdings:
        holding = holdings_by_id.get(item.holding_id)
        if holding is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"종목 {item.holding_id}이 이 포트폴리오에 없습니다."
            )
        holding.quantity = item.quantity
        holding.target_weight = item.target_weight
    portfolio.cash_ratio = payload.cash_ratio

    after_snapshot = {
        str(h.id): {"ticker": h.ticker, "quantity": h.quantity, "target_weight": h.target_weight}
        for h in portfolio.holdings
    }

    transaction = orm.Transaction(
        portfolio_id=portfolio.id,
        type=orm.TransactionType.REBALANCE,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        note=payload.note,
    )
    db.add(transaction)
    await db.commit()
    await db.refresh(transaction)
    return transaction
