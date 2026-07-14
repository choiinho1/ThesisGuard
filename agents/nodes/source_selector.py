"""Deterministic candidate filtering before model-backed evidence classification."""

from __future__ import annotations

from langgraph.runtime import Runtime

from agents.retrieval import limit_documents_by_source, preselect_documents
from agents.runtime import AgentDependencies
from agents.state import AnalysisState


async def select_sources(state: AnalysisState, runtime: Runtime[AgentDependencies]) -> dict:
    config = runtime.context.config
    source_limits = {
        "filings": config.max_selected_filings,
        "news": config.max_selected_news,
        "macro": config.max_selected_macro,
    }
    candidate_multiplier = (
        config.rag_candidate_multiplier if runtime.context.retriever is not None else 1
    )
    candidates = preselect_documents(
        state["research_data"],
        ticker=state["ticker"],
        thesis=state["thesis_snapshot"],
        focus_points=state.get("focus_points", []),
        lookback_days=config.news_lookback_days,
        min_news_score=config.min_news_selection_score,
        source_limits={key: value * candidate_multiplier for key, value in source_limits.items()},
    )
    if runtime.context.retriever is None:
        return {"selected_documents": candidates}
    try:
        documents = await runtime.context.retriever.select_documents(
            ticker=state["ticker"],
            thesis=state["thesis_snapshot"],
            focus_points=state.get("focus_points", []),
            documents=candidates,
            source_limits=source_limits,
        )
    except Exception:  # noqa: BLE001 - RAG failure must retain deterministic retrieval
        documents = limit_documents_by_source(candidates, source_limits)
    return {"selected_documents": documents}
