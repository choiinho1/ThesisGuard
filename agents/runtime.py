"""Runtime dependencies passed to LangGraph nodes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from agents.contracts import AnalysisModel, ContextProvider, ResearchTools

ModelResult = TypeVar("ModelResult")


@dataclass(frozen=True, slots=True)
class WorkflowConfig:
    max_research_rounds: int = 2
    min_grounded_evidence: int = 2
    model_max_attempts: int = 2

    def __post_init__(self) -> None:
        if self.max_research_rounds < 1:
            raise ValueError("max_research_rounds must be at least 1")
        if self.min_grounded_evidence < 1:
            raise ValueError("min_grounded_evidence must be at least 1")
        if self.model_max_attempts < 1:
            raise ValueError("model_max_attempts must be at least 1")


@dataclass(frozen=True, slots=True)
class AgentDependencies:
    context_provider: ContextProvider
    research_tools: ResearchTools
    model: AnalysisModel
    config: WorkflowConfig


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
