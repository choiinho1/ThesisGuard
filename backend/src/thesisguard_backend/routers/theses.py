"""Thesis registration (natural language -> structured via C), read/update, history."""

from __future__ import annotations

import uuid
from typing import Annotated

from agents.scoring import prepare_structured_thesis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from thesisguard_backend import models as orm
from thesisguard_backend.deps import Agent, CurrentUser, DbSession
from thesisguard_backend.observability import observe_llm_operation
from thesisguard_backend.routers.holdings import OwnedHolding
from thesisguard_backend.schemas import (
    ThesisCreateRequest,
    ThesisResponse,
    ThesisUpdateRequest,
    ThesisVersionResponse,
)

router = APIRouter(tags=["theses"])


async def get_owned_thesis(
    thesis_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> orm.Thesis:
    thesis = await db.get(orm.Thesis, thesis_id)
    if thesis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thesis를 찾을 수 없습니다.")
    holding = await db.get(orm.Holding, thesis.holding_id)
    portfolio = await db.get(orm.Portfolio, holding.portfolio_id) if holding else None
    if portfolio is None or portfolio.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thesis를 찾을 수 없습니다.")
    return thesis


OwnedThesis = Annotated[orm.Thesis, Depends(get_owned_thesis)]


@router.post(
    "/api/holdings/{holding_id}/thesis",
    response_model=ThesisResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_thesis(
    payload: ThesisCreateRequest,
    holding: OwnedHolding,
    db: DbSession,
    agent: Agent,
    current_user: CurrentUser,
) -> orm.Thesis:
    with observe_llm_operation(
        "thesisguard.structure-thesis",
        user_id=str(current_user.id),
        session_id=f"portfolio:{holding.portfolio_id}",
        input={
            "holding_id": str(holding.id),
            "ticker": holding.ticker,
            "raw_input": payload.raw_input,
        },
        metadata={
            "portfolio_id": holding.portfolio_id,
            "holding_id": holding.id,
            "ticker": holding.ticker,
        },
        tags=["thesis-structure", holding.ticker.lower()],
    ) as trace:
        structured = await agent.astructure_thesis(
            payload.raw_input, runnable_config=trace.runnable_config
        )
        structured = prepare_structured_thesis(structured)
        trace.set_output(structured.model_dump(mode="json"))
    thesis = orm.Thesis(
        holding_id=holding.id,
        raw_input=structured.raw_input,
        main_thesis=structured.main_thesis,
        key_assumptions=structured.key_assumptions,
        positive_signals=structured.positive_signals,
        negative_signals=structured.negative_signals,
        key_risks=structured.key_risks,
        template_id="GENERAL_FUNDAMENTAL",
        template_catalog_version="deprecated",
        template_snapshot={},
        assumption_bindings=[],
        logic_graph=structured.logic_graph.model_dump(mode="json"),
        score_breakdown=(
            structured.score_breakdown.model_dump(mode="json") if structured.score_breakdown else {}
        ),
        confidence_score=structured.confidence_score,
        status=structured.status,
    )
    db.add(thesis)
    await db.commit()
    await db.refresh(thesis)
    return thesis


@router.get("/api/theses/{thesis_id}", response_model=ThesisResponse)
async def get_thesis(thesis: OwnedThesis) -> orm.Thesis:
    return thesis


@router.put("/api/theses/{thesis_id}", response_model=ThesisResponse)
async def update_thesis(
    payload: ThesisUpdateRequest,
    thesis: OwnedThesis,
    db: DbSession,
    agent: Agent,
    current_user: CurrentUser,
) -> orm.Thesis:
    values = payload.model_dump(exclude_unset=True)
    raw_input = values.pop("raw_input", None)
    if raw_input is not None:
        holding = await db.get(orm.Holding, thesis.holding_id)
        assert holding is not None
        with observe_llm_operation(
            "thesisguard.structure-thesis",
            user_id=str(current_user.id),
            session_id=f"portfolio:{holding.portfolio_id}",
            input={
                "thesis_id": str(thesis.id),
                "holding_id": str(holding.id),
                "ticker": holding.ticker,
                "raw_input": raw_input,
            },
            metadata={
                "portfolio_id": holding.portfolio_id,
                "holding_id": holding.id,
                "thesis_id": thesis.id,
                "ticker": holding.ticker,
                "operation": "update",
            },
            tags=["thesis-structure", "thesis-update", holding.ticker.lower()],
        ) as trace:
            structured = await agent.astructure_thesis(
                raw_input, runnable_config=trace.runnable_config
            )
            structured = prepare_structured_thesis(structured)
            trace.set_output(structured.model_dump(mode="json"))
        thesis.raw_input = structured.raw_input
        thesis.main_thesis = structured.main_thesis
        thesis.key_assumptions = structured.key_assumptions
        thesis.positive_signals = structured.positive_signals
        thesis.negative_signals = structured.negative_signals
        thesis.key_risks = structured.key_risks
        thesis.template_id = "GENERAL_FUNDAMENTAL"
        thesis.template_catalog_version = "deprecated"
        thesis.template_snapshot = {}
        thesis.assumption_bindings = []
        thesis.logic_graph = structured.logic_graph.model_dump(mode="json")
        thesis.score_breakdown = (
            structured.score_breakdown.model_dump(mode="json") if structured.score_breakdown else {}
        )
        thesis.confidence_score = structured.confidence_score
        thesis.status = structured.status
    for field, value in values.items():
        setattr(thesis, field, value)
    await db.commit()
    await db.refresh(thesis)
    return thesis


@router.get("/api/theses/{thesis_id}/history", response_model=list[ThesisVersionResponse])
async def get_thesis_history(thesis: OwnedThesis, db: DbSession) -> list[orm.ThesisVersion]:
    result = await db.scalars(
        select(orm.ThesisVersion)
        .where(orm.ThesisVersion.thesis_id == thesis.id)
        .order_by(orm.ThesisVersion.version_no)
    )
    return list(result)
