from __future__ import annotations

import pytest

from agents.graph import ThesisGuardAgent
from agents.model import LangChainAnalysisModel
from agents.models import StructuredThesis, ThesisStatus
from agents.runnable_context import get_model_runnable_config


def _structured_thesis() -> StructuredThesis:
    return StructuredThesis(
        raw_input="AI infrastructure spending will grow.",
        main_thesis="AI infrastructure spending growth",
        key_assumptions=["Infrastructure budgets continue to grow."],
        confidence_score=50,
        status=ThesisStatus.UNCHANGED,
    )


class CapturingRunnable:
    def __init__(self) -> None:
        self.config = None

    async def ainvoke(self, messages, config=None):
        self.config = config
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
    assert runnable.config == config
    assert get_model_runnable_config() is None
