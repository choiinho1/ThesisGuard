from __future__ import annotations

import pytest

from agents.graph import ThesisGuardAgent
from agents.model import LangChainAnalysisModel
from agents.models import AssumptionBinding, StructuredThesis, ThesisStatus
from agents.runnable_context import get_model_runnable_config
from agents.thesis_templates import ThesisTemplateId


def _structured_thesis() -> StructuredThesis:
    return StructuredThesis(
        raw_input="AI infrastructure spending will grow.",
        main_thesis="AI infrastructure spending growth",
        key_assumptions=["Infrastructure budgets continue to grow."],
        template_id=ThesisTemplateId.SCALABLE_GROWTH,
        assumption_bindings=[
            AssumptionBinding(
                slot_id="market_demand",
                assumptions=["Infrastructure budgets continue to grow."],
            )
        ],
        confidence_score=50,
        status=ThesisStatus.UNCHANGED,
    )


class CapturingRunnable:
    def __init__(self) -> None:
        self.config = None
        self.messages = None

    async def ainvoke(self, messages, config=None):
        self.config = config
        self.messages = messages
        return _structured_thesis()


class CapturingChatModel:
    def __init__(self, runnable: CapturingRunnable) -> None:
        self.runnable = runnable

    def with_structured_output(self, schema):
        return self.runnable


@pytest.mark.asyncio
async def test_direct_model_call_receives_request_local_runnable_config() -> None:
    runnable = CapturingRunnable()
    model = LangChainAnalysisModel(CapturingChatModel(runnable))  # type: ignore[arg-type]
    agent = ThesisGuardAgent(
        context_provider=object(),  # type: ignore[arg-type]
        research_tools=object(),  # type: ignore[arg-type]
        model=model,
    )
    config = {"callbacks": [], "run_name": "test-structure-thesis"}

    result = await agent.astructure_thesis(
        "AI infrastructure spending will grow.", runnable_config=config
    )

    assert result.main_thesis == "AI infrastructure spending growth"
    assert result.template_id == ThesisTemplateId.SCALABLE_GROWTH
    assert result.assumption_bindings[0].assumptions == ["Infrastructure budgets continue to grow."]
    assert result.score_breakdown is not None
    assert result.score_breakdown.health_score == 50
    assert runnable.config == config
    assert runnable.messages is not None
    assert "SCALABLE_GROWTH" in str(runnable.messages[-1].content)
    assert "GENERAL_FUNDAMENTAL" in str(runnable.messages[-1].content)
    assert get_model_runnable_config() is None
