"""Shared helpers for research nodes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langgraph.runtime import Runtime

from agents.models import ResearchRequest, SourceDocument
from agents.runtime import AgentDependencies
from agents.state import AnalysisState, ResearchData, empty_research_data


def research_request(state: AnalysisState) -> ResearchRequest:
    return ResearchRequest(
        portfolio_id=state["portfolio_id"],
        holding_id=state["holding_id"],
        ticker=state["ticker"],
        thesis=state["thesis_snapshot"],
        round_no=state["research_round"],
        focus_points=state.get("focus_points", []),
    )


async def run_research_tool(
    state: AnalysisState,
    runtime: Runtime[AgentDependencies],
    key: str,
    method: Callable[[ResearchRequest], Awaitable[list[SourceDocument]]],
) -> dict:
    try:
        documents = await method(research_request(state))
        research_data: ResearchData = empty_research_data()
        research_data[key] = documents  # type: ignore[literal-required]
        return {"research_data": research_data}
    except Exception as exc:
        return {"source_errors": [f"{key}: {type(exc).__name__}: {exc}"]}
