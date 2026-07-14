"""Dependency ports implemented by Backend(B) or the selected LLM provider."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from agents.models import (
    AnalysisContext,
    DebateReport,
    EvidenceAssessment,
    EvidenceItem,
    JudgeDecision,
    PortfolioAnalysis,
    PortfolioQueryAnswer,
    PortfolioThesis,
    ResearchRequest,
    SourceDocument,
    StructuredThesis,
)


class ContextProvider(Protocol):
    async def load_analysis_context(
        self, portfolio_id: str, holding_id: str
    ) -> AnalysisContext: ...

    async def load_portfolio_theses(self, portfolio_id: str) -> list[PortfolioThesis]: ...


class ResearchTools(Protocol):
    """B wraps backend/mcp_tools functions behind this boundary."""

    async def get_filings(self, request: ResearchRequest) -> list[SourceDocument]: ...

    async def get_news(self, request: ResearchRequest) -> list[SourceDocument]: ...

    async def get_macro(self, request: ResearchRequest) -> list[SourceDocument]: ...


class EmbeddingModel(Protocol):
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def aembed_query(self, text: str) -> list[float]: ...


class DocumentRetriever(Protocol):
    async def select_documents(
        self,
        *,
        ticker: str,
        thesis: StructuredThesis,
        focus_points: Sequence[str],
        documents: Sequence[SourceDocument],
        source_limits: dict[str, int],
    ) -> list[SourceDocument]: ...


class AnalysisModel(Protocol):
    async def structure_thesis(self, raw_input: str) -> StructuredThesis: ...

    async def classify_evidence(
        self, thesis: StructuredThesis, document: SourceDocument
    ) -> EvidenceAssessment: ...

    async def build_bull_report(
        self, thesis: StructuredThesis, evidence: list[EvidenceItem]
    ) -> DebateReport: ...

    async def build_bear_report(
        self, thesis: StructuredThesis, evidence: list[EvidenceItem]
    ) -> DebateReport: ...

    async def judge(
        self,
        thesis: StructuredThesis,
        evidence: list[EvidenceItem],
        bull_report: DebateReport,
        bear_report: DebateReport,
    ) -> JudgeDecision: ...

    async def analyze_portfolio(
        self, portfolio_theses: list[PortfolioThesis]
    ) -> PortfolioAnalysis: ...

    async def answer_portfolio_query(
        self,
        question: str,
        portfolio_theses: list[PortfolioThesis],
        evidence: list[EvidenceItem],
    ) -> PortfolioQueryAnswer: ...
