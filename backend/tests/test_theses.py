from __future__ import annotations

import pytest
from agents.models import LogicOperator, StructuredThesis, ThesisLogicGraph, ThesisLogicNode
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from thesisguard_backend import models as orm
from thesisguard_backend.db import Base
from thesisguard_backend.routers.theses import create_thesis, update_thesis
from thesisguard_backend.schemas import ThesisCreateRequest, ThesisUpdateRequest


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


class GraphStructuringAgent:
    def __init__(self, operator: LogicOperator) -> None:
        self.operator = operator
        self.calls: list[str] = []

    async def astructure_thesis(self, raw_input: str, *, runnable_config=None) -> StructuredThesis:
        self.calls.append(raw_input)
        assumption = "A measurable assumption remains valid"
        return StructuredThesis(
            raw_input=raw_input,
            main_thesis=f"{self.operator.value} investment thesis",
            key_assumptions=[assumption],
            logic_graph=ThesisLogicGraph(
                root_id="root_claim",
                nodes=[
                    ThesisLogicNode(
                        node_id="root_claim",
                        kind="CLAIM",
                        label=f"{self.operator.value} investment thesis",
                        operator=self.operator,
                        child_ids=["measurable_assumption"],
                    ),
                    ThesisLogicNode(
                        node_id="measurable_assumption",
                        kind="ASSUMPTION",
                        label=assumption,
                        assumption=assumption,
                    ),
                ],
            ),
        )


class FailingStructuringAgent:
    async def astructure_thesis(self, raw_input: str, *, runnable_config=None):
        raise RuntimeError("provider unavailable")


async def _owned_holding(db_session) -> tuple[orm.User, orm.Holding]:
    user = orm.User(email="graph@example.com", password_hash="h")
    portfolio = orm.Portfolio(user=user, name="Graph portfolio")
    holding = orm.Holding(
        portfolio=portfolio,
        ticker="NVDA",
        quantity=1,
        avg_buy_price=1,
    )
    db_session.add(holding)
    await db_session.commit()
    return user, holding


@pytest.mark.asyncio
async def test_create_thesis_persists_causal_graph_and_neutral_score(db_session) -> None:
    user, holding = await _owned_holding(db_session)
    agent = GraphStructuringAgent(LogicOperator.AND)

    thesis = await create_thesis(
        ThesisCreateRequest(raw_input="AI infrastructure demand will keep expanding."),
        holding,
        db_session,
        agent,  # type: ignore[arg-type]
        user,
    )

    assert thesis.logic_graph["root_id"] == "root_claim"
    assert thesis.logic_graph["nodes"][0]["operator"] == "AND"
    assert thesis.score_breakdown["scoring_method"] == "EVIDENCE_NODE_MATRIX_V2"
    assert thesis.score_breakdown["health_score"] == 0
    assert thesis.template_catalog_version == "deprecated"


@pytest.mark.asyncio
async def test_create_thesis_returns_actionable_gateway_error_when_llm_fails(db_session) -> None:
    user, holding = await _owned_holding(db_session)

    with pytest.raises(HTTPException) as caught:
        await create_thesis(
            ThesisCreateRequest(raw_input="AI infrastructure demand will keep expanding."),
            holding,
            db_session,
            FailingStructuringAgent(),  # type: ignore[arg-type]
            user,
        )

    assert caught.value.status_code == status.HTTP_502_BAD_GATEWAY
    assert "LLM API 키·할당량·네트워크" in caught.value.detail


@pytest.mark.asyncio
async def test_resetting_raw_thesis_rebuilds_graph_and_resets_score(db_session) -> None:
    user, holding = await _owned_holding(db_session)
    thesis = await create_thesis(
        ThesisCreateRequest(raw_input="AI infrastructure demand will keep expanding."),
        holding,
        db_session,
        GraphStructuringAgent(LogicOperator.AND),  # type: ignore[arg-type]
        user,
    )
    reset_agent = GraphStructuringAgent(LogicOperator.OR)

    updated = await update_thesis(
        ThesisUpdateRequest(raw_input="Alternative routes can restore the business."),
        thesis,
        db_session,
        reset_agent,  # type: ignore[arg-type]
        user,
    )

    assert reset_agent.calls == ["Alternative routes can restore the business."]
    assert updated.logic_graph["nodes"][0]["operator"] == "OR"
    assert updated.confidence_score == 0
    assert updated.status == "UNCHANGED"
    assert updated.score_breakdown["root_state"] == 0
    assert updated.score_breakdown["is_broken"] is False
