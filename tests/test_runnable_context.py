from __future__ import annotations

import pytest

from agents.graph import ThesisGuardAgent
from agents.model import LangChainAnalysisModel
from agents.models import (
    LogicOperator,
    StructuredThesis,
    ThesisLogicGraph,
    ThesisLogicNode,
    ThesisStatus,
)
from agents.runnable_context import get_model_runnable_config


def _structured_thesis() -> StructuredThesis:
    return StructuredThesis(
        raw_input="AI infrastructure spending will grow.",
        main_thesis="AI infrastructure spending growth",
        key_assumptions=["Infrastructure budgets continue to grow."],
        logic_graph=ThesisLogicGraph(
            root_id="root_claim",
            nodes=[
                ThesisLogicNode(
                    node_id="root_claim",
                    kind="CLAIM",
                    label="AI infrastructure spending growth",
                    operator=LogicOperator.AND,
                    child_ids=["budget_growth"],
                ),
                ThesisLogicNode(
                    node_id="budget_growth",
                    kind="ASSUMPTION",
                    label="Infrastructure budgets continue to grow.",
                    assumption="Infrastructure budgets continue to grow.",
                ),
            ],
        ),
        confidence_score=0,
        status=ThesisStatus.UNCHANGED,
    )


def _strengthened_thesis() -> StructuredThesis:
    assumptions = [
        "Infrastructure budgets continue to grow.",
        "Budget growth converts into measurable supplier revenue.",
    ]
    return StructuredThesis(
        raw_input="AI infrastructure spending will grow.",
        main_thesis="AI infrastructure spending produces durable supplier growth",
        key_assumptions=assumptions,
        positive_signals=["Reported infrastructure budget growth"],
        negative_signals=["Budget reductions or delayed deployments"],
        key_risks=["Spending growth does not convert into supplier revenue"],
        logic_graph=ThesisLogicGraph(
            root_id="root_claim",
            nodes=[
                ThesisLogicNode(
                    node_id="root_claim",
                    kind="CLAIM",
                    label="AI infrastructure spending produces durable supplier growth",
                    operator=LogicOperator.AND,
                    child_ids=["budget_growth", "revenue_conversion"],
                ),
                ThesisLogicNode(
                    node_id="budget_growth",
                    kind="ASSUMPTION",
                    label=assumptions[0],
                    assumption=assumptions[0],
                ),
                ThesisLogicNode(
                    node_id="revenue_conversion",
                    kind="ASSUMPTION",
                    label=assumptions[1],
                    assumption=assumptions[1],
                ),
            ],
        ),
    )


class CapturingRunnable:
    def __init__(self) -> None:
        self.config = None
        self.messages = None
        self.calls = []

    async def ainvoke(self, messages, config=None):
        self.config = config
        self.messages = messages
        self.calls.append((messages, config))
        return _strengthened_thesis() if len(self.calls) == 2 else _structured_thesis()


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

    assert result.main_thesis == "AI infrastructure spending produces durable supplier growth"
    assert result.logic_graph is not None
    assert result.logic_graph.root_id == "root_claim"
    assert result.logic_graph.nodes[1].assumption == "Infrastructure budgets continue to grow."
    assert result.logic_graph.nodes[2].assumption == (
        "Budget growth converts into measurable supplier revenue."
    )
    assert result.score_breakdown is not None
    assert result.score_breakdown.health_score == 0
    assert runnable.config == config
    assert runnable.messages is not None
    assert len(runnable.calls) == 2
    assert "Thesis Strengthening Agent" in str(runnable.calls[-1][0][-1].content)
    assert "AND" in str(runnable.messages[-1].content)
    assert "CONTRIBUTING" in str(runnable.messages[-1].content)
    assert get_model_runnable_config() is None
