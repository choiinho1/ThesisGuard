"""LangGraph assembly and the Backend(B) entry point."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, Literal, TypeVar

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from agents.contracts import AnalysisModel, ContextProvider, ResearchTools
from agents.models import (
    EvidenceItem,
    PortfolioQueryAnswer,
    StructuredThesis,
    ThesisAnalysisResult,
)
from agents.nodes.alert import alert_decision
from agents.nodes.debate import (
    bear_agent,
    bull_agent,
    debate_start,
    judge_agent,
)
from agents.nodes.evidence import classify_evidence
from agents.nodes.filing_agent import filing_agent
from agents.nodes.finalize import finalize
from agents.nodes.macro_agent import macro_agent
from agents.nodes.news_agent import news_agent
from agents.nodes.portfolio import portfolio_agent
from agents.nodes.router import prepare_research, request_router
from agents.runnable_context import use_model_runnable_config
from agents.runtime import AgentDependencies, WorkflowConfig, call_model
from agents.state import AnalysisState, empty_research_data

ResultT = TypeVar("ResultT")


def build_analysis_graph(config: WorkflowConfig):
    graph = StateGraph(AnalysisState, context_schema=AgentDependencies)
    graph.add_node("request_router", request_router)
    graph.add_node("prepare_research", prepare_research)
    graph.add_node("filing_agent", filing_agent)
    graph.add_node("news_agent", news_agent)
    graph.add_node("macro_agent", macro_agent)
    graph.add_node("evidence_classifier", classify_evidence)
    graph.add_node("debate_start", debate_start)
    graph.add_node("bull_agent", bull_agent)
    graph.add_node("bear_agent", bear_agent)
    graph.add_node("judge_agent", judge_agent)
    graph.add_node("portfolio_agent", portfolio_agent)
    graph.add_node("alert_decision", alert_decision)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "request_router")
    graph.add_edge("request_router", "prepare_research")
    graph.add_edge("prepare_research", "filing_agent")
    graph.add_edge("prepare_research", "news_agent")
    graph.add_edge("prepare_research", "macro_agent")
    graph.add_edge(["filing_agent", "news_agent", "macro_agent"], "evidence_classifier")

    def route_after_classification(
        state: AnalysisState,
    ) -> Literal["retry", "debate"]:
        if state["needs_more_research"] and state["research_round"] < config.max_research_rounds:
            return "retry"
        return "debate"

    graph.add_conditional_edges(
        "evidence_classifier",
        route_after_classification,
        {"retry": "prepare_research", "debate": "debate_start"},
    )
    graph.add_edge("debate_start", "bull_agent")
    graph.add_edge("debate_start", "bear_agent")
    graph.add_edge(["bull_agent", "bear_agent"], "judge_agent")
    graph.add_edge("judge_agent", "portfolio_agent")
    graph.add_edge("portfolio_agent", "alert_decision")
    graph.add_edge("alert_decision", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


class ThesisGuardAgent:
    """AI-owned service configured with Backend MCP and context adapters."""

    def __init__(
        self,
        *,
        context_provider: ContextProvider,
        research_tools: ResearchTools,
        model: AnalysisModel,
        config: WorkflowConfig | None = None,
    ) -> None:
        self.config = config or WorkflowConfig()
        self.dependencies = AgentDependencies(
            context_provider=context_provider,
            research_tools=research_tools,
            model=model,
            config=self.config,
        )
        self.graph = build_analysis_graph(self.config)

    async def arun_analysis_workflow(
        self,
        portfolio_id: str,
        holding_id: str,
        *,
        runnable_config: RunnableConfig | None = None,
    ) -> ThesisAnalysisResult:
        graph_config: RunnableConfig = {
            **(runnable_config or {}),
            "recursion_limit": 30,
        }
        final_state = await self.graph.ainvoke(
            {
                "portfolio_id": portfolio_id,
                "holding_id": holding_id,
                "research_round": 0,
                "focus_points": [],
                "research_data": empty_research_data(),
                "source_errors": [],
            },
            context=self.dependencies,
            config=graph_config,
        )
        return final_state["result"]

    def run_analysis_workflow(
        self,
        portfolio_id: str,
        holding_id: str,
        *,
        runnable_config: RunnableConfig | None = None,
    ) -> ThesisAnalysisResult:
        return _run_sync(
            self.arun_analysis_workflow(portfolio_id, holding_id, runnable_config=runnable_config)
        )

    async def astructure_thesis(
        self,
        raw_input: str,
        *,
        runnable_config: RunnableConfig | None = None,
    ) -> StructuredThesis:
        with use_model_runnable_config(runnable_config):
            return await call_model(
                self.dependencies, self.dependencies.model.structure_thesis, raw_input
            )

    def structure_thesis(
        self,
        raw_input: str,
        *,
        runnable_config: RunnableConfig | None = None,
    ) -> StructuredThesis:
        return _run_sync(self.astructure_thesis(raw_input, runnable_config=runnable_config))

    async def aanswer_portfolio_query(
        self,
        portfolio_id: str,
        question: str,
        evidence: list[EvidenceItem] | None = None,
        *,
        runnable_config: RunnableConfig | None = None,
    ) -> PortfolioQueryAnswer:
        portfolio_theses = await self.dependencies.context_provider.load_portfolio_theses(
            portfolio_id
        )
        with use_model_runnable_config(runnable_config):
            return await call_model(
                self.dependencies,
                self.dependencies.model.answer_portfolio_query,
                question,
                portfolio_theses,
                evidence or [],
            )

    def answer_portfolio_query(
        self,
        portfolio_id: str,
        question: str,
        evidence: list[EvidenceItem] | None = None,
        *,
        runnable_config: RunnableConfig | None = None,
    ) -> PortfolioQueryAnswer:
        return _run_sync(
            self.aanswer_portfolio_query(
                portfolio_id,
                question,
                evidence,
                runnable_config=runnable_config,
            )
        )


def _run_sync(coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    coroutine.close()
    raise RuntimeError("Use the async entry point inside an existing event loop")


_default_agent: ThesisGuardAgent | None = None


def configure_agent(agent: ThesisGuardAgent) -> None:
    global _default_agent
    _default_agent = agent


def _agent() -> ThesisGuardAgent:
    if _default_agent is None:
        raise RuntimeError("Call configure_agent() during Backend application startup")
    return _default_agent


def run_analysis_workflow(
    portfolio_id: str,
    holding_id: str,
    *,
    runnable_config: RunnableConfig | None = None,
) -> ThesisAnalysisResult:
    """Team-guide contract imported directly by Backend(B)."""

    return _agent().run_analysis_workflow(portfolio_id, holding_id, runnable_config=runnable_config)


async def arun_analysis_workflow(
    portfolio_id: str,
    holding_id: str,
    *,
    runnable_config: RunnableConfig | None = None,
) -> ThesisAnalysisResult:
    return await _agent().arun_analysis_workflow(
        portfolio_id, holding_id, runnable_config=runnable_config
    )
