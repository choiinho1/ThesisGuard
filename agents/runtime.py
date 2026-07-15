"""Runtime dependencies passed to LangGraph nodes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from agents.contracts import AnalysisModel, ContextProvider, DocumentRetriever, ResearchTools

ModelResult = TypeVar("ModelResult")


@dataclass(frozen=True, slots=True)
class WorkflowConfig:
    max_research_rounds: int = 2
    min_grounded_evidence: int = 2
    model_max_attempts: int = 2
    min_relevance_score: float = 0.55
    min_news_selection_score: float = 0.30
    news_lookback_days: int = 30
    news_candidate_limit: int = 15
    max_selected_filings: int = 3
    max_selected_news: int = 5
    max_selected_macro: int = 2
    rag_candidate_multiplier: int = 3

    def __post_init__(self) -> None:
        if self.max_research_rounds < 1:
            raise ValueError("max_research_rounds must be at least 1")
        if self.min_grounded_evidence < 1:
            raise ValueError("min_grounded_evidence must be at least 1")
        if self.model_max_attempts < 1:
            raise ValueError("model_max_attempts must be at least 1")
        if not 0 <= self.min_relevance_score <= 1:
            raise ValueError("min_relevance_score must be between 0 and 1")
        if not 0 <= self.min_news_selection_score <= 1:
            raise ValueError("min_news_selection_score must be between 0 and 1")
        if not 1 <= self.news_lookback_days <= 30:
            raise ValueError("news_lookback_days must be between 1 and 30")
        if not 1 <= self.news_candidate_limit <= 50:
            raise ValueError("news_candidate_limit must be between 1 and 50")
        if (
            min(
                self.max_selected_filings,
                self.max_selected_news,
                self.max_selected_macro,
            )
            < 0
        ):
            raise ValueError("selected source limits cannot be negative")
        if self.rag_candidate_multiplier < 1:
            raise ValueError("rag_candidate_multiplier must be at least 1")


@dataclass(frozen=True, slots=True)
class AgentDependencies:
    context_provider: ContextProvider
    research_tools: ResearchTools
    model: AnalysisModel
    config: WorkflowConfig
    retriever: DocumentRetriever | None = None


async def call_model(
    dependencies: AgentDependencies,
    method: Callable[..., Awaitable[ModelResult]],
    *args: object,
) -> ModelResult:
    error: Exception | None = None
    for _ in range(dependencies.config.model_max_attempts):
        try:
            return await method(*args)
        except Exception as exc:
            error = exc
    assert error is not None
    raise error
