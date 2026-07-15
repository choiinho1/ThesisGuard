from __future__ import annotations

import pytest
from agents.models import AssumptionBinding, StructuredThesis
from agents.thesis_templates import (
    THESIS_TEMPLATE_CATALOG_VERSION,
    ThesisTemplateId,
    get_thesis_template,
)
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


class TemplateSelectingAgent:
    def __init__(self, template_id: ThesisTemplateId) -> None:
        self.template_id = template_id
        self.calls: list[str] = []

    async def astructure_thesis(self, raw_input: str, *, runnable_config=None) -> StructuredThesis:
        self.calls.append(raw_input)
        assumption = "A measurable assumption remains valid"
        first_slot = get_thesis_template(self.template_id).assumption_slots[0].slot_id
        return StructuredThesis(
            raw_input=raw_input,
            main_thesis=f"{self.template_id.value} investment thesis",
            key_assumptions=[assumption],
            template_id=self.template_id,
            assumption_bindings=[AssumptionBinding(slot_id=first_slot, assumptions=[assumption])],
        )


async def _owned_holding(db_session) -> tuple[orm.User, orm.Holding]:
    user = orm.User(email="template@example.com", password_hash="h")
    portfolio = orm.Portfolio(user=user, name="Template portfolio")
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
async def test_create_thesis_persists_selected_template_snapshot(db_session) -> None:
    user, holding = await _owned_holding(db_session)
    agent = TemplateSelectingAgent(ThesisTemplateId.SCALABLE_GROWTH)

    thesis = await create_thesis(
        ThesisCreateRequest(raw_input="AI infrastructure demand will keep expanding."),
        holding,
        db_session,
        agent,  # type: ignore[arg-type]
        user,
    )

    assert thesis.template_id == "SCALABLE_GROWTH"
    assert thesis.template_catalog_version == THESIS_TEMPLATE_CATALOG_VERSION
    assert thesis.template_snapshot["template_id"] == "SCALABLE_GROWTH"
    assert (
        sum(slot["weight_bps"] for slot in thesis.template_snapshot["assumption_slots"]) == 10_000
    )
    assert thesis.assumption_bindings[0]["assumptions"] == ["A measurable assumption remains valid"]
    assert thesis.score_breakdown["health_score"] == 50


@pytest.mark.asyncio
async def test_resetting_raw_thesis_reselects_and_replaces_template_snapshot(db_session) -> None:
    user, holding = await _owned_holding(db_session)
    create_agent = TemplateSelectingAgent(ThesisTemplateId.SCALABLE_GROWTH)
    thesis = await create_thesis(
        ThesisCreateRequest(raw_input="AI infrastructure demand will keep expanding."),
        holding,
        db_session,
        create_agent,  # type: ignore[arg-type]
        user,
    )
    reset_agent = TemplateSelectingAgent(ThesisTemplateId.TURNAROUND)

    updated = await update_thesis(
        ThesisUpdateRequest(raw_input="Liquidity and restructuring must restore the business."),
        thesis,
        db_session,
        reset_agent,  # type: ignore[arg-type]
        user,
    )

    assert reset_agent.calls == ["Liquidity and restructuring must restore the business."]
    assert updated.template_id == "TURNAROUND"
    assert updated.confidence_score == 50
    assert updated.status == "UNCHANGED"
    assert updated.template_snapshot["template_id"] == "TURNAROUND"
    core_slots = [
        slot["slot_id"] for slot in updated.template_snapshot["assumption_slots"] if slot["core"]
    ]
    assert core_slots == ["execution_milestones", "liquidity_runway"]
