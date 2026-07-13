"""Stable module-level API for Backend(B) integration."""

from __future__ import annotations

from thesisguard_agent.models import StructuredThesis, ThesisAnalysisResult
from thesisguard_agent.workflow import ThesisGuardAgent

_default_agent: ThesisGuardAgent | None = None


def configure_default_agent(agent: ThesisGuardAgent) -> None:
    """Configure dependencies once during FastAPI application startup."""

    global _default_agent
    _default_agent = agent


def _agent() -> ThesisGuardAgent:
    if _default_agent is None:
        raise RuntimeError("Call configure_default_agent() during application startup")
    return _default_agent


async def structure_thesis(raw_input: str) -> StructuredThesis:
    return await _agent().structure_thesis(raw_input)


async def run_analysis_workflow(
    portfolio_id: str, holding_id: str
) -> ThesisAnalysisResult:
    """TDD contract: analyze one holding and return a DB-ready Pydantic result."""

    return await _agent().run_analysis_workflow(portfolio_id, holding_id)
