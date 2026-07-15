"""Request Router and research-round preparation."""

from langgraph.runtime import Runtime

from agents.runtime import AgentDependencies
from agents.state import AnalysisState


async def request_router(state: AnalysisState, runtime: Runtime[AgentDependencies]) -> dict:
    context = await runtime.context.context_provider.load_analysis_context(
        state["portfolio_id"], state["holding_id"]
    )
    identifiers_match = (
        context.portfolio_id == state["portfolio_id"] and context.holding_id == state["holding_id"]
    )
    if not identifiers_match:
        raise ValueError("Context provider returned a different analysis request")
    return {
        "ticker": context.ticker,
        "thesis_snapshot": context.thesis,
        "portfolio_theses": context.portfolio_theses,
        "evidence_history_summary": context.evidence_history_summary,
        "evidence_history_document_ids": context.evidence_history_document_ids,
        "evidence_history_source_urls": context.evidence_history_source_urls,
        "focus_points": context.thesis.key_assumptions,
    }


def prepare_research(state: AnalysisState) -> dict:
    return {"research_round": state["research_round"] + 1}
