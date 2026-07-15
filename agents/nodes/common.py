"""Shared helpers for research nodes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langgraph.runtime import Runtime

from agents.models import ResearchRequest, SourceDocument
from agents.runtime import AgentDependencies
from agents.state import AnalysisState, ResearchData, empty_research_data


def research_request(state: AnalysisState, runtime: Runtime[AgentDependencies]) -> ResearchRequest:
    return ResearchRequest(
        portfolio_id=state["portfolio_id"],
        holding_id=state["holding_id"],
        ticker=state["ticker"],
        thesis=state["thesis_snapshot"],
        round_no=state["research_round"],
        focus_points=state.get("focus_points", []),
        lookback_days=runtime.context.config.news_lookback_days,
        candidate_limit=runtime.context.config.news_candidate_limit,
    )


async def run_research_tool(
    state: AnalysisState,
    runtime: Runtime[AgentDependencies],
    key: str,
    method: Callable[[ResearchRequest], Awaitable[list[SourceDocument]]],
) -> dict:
    try:
        documents = await method(research_request(state, runtime))
        research_data: ResearchData = empty_research_data()
        research_data[key] = documents  # type: ignore[literal-required]
        result: dict = {"research_data": research_data}
        if not documents:
            result["source_errors"] = [f"{key}: no documents returned"]
        return result
    except Exception as exc:
        return {"source_errors": [f"{key}: {type(exc).__name__}: {exc}"]}
