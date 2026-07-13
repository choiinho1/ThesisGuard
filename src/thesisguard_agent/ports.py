"""Dependency ports owned by Backend(B) or the selected LLM provider."""

from __future__ import annotations

from typing import Protocol

from thesisguard_agent.models import (
    AnalysisContext,
    DebateReport,
    EvidenceAssessment,
    EvidenceItem,
    JudgeDecision,
    PortfolioAnalysis,
    PortfolioThesis,
    ResearchRequest,
    SourceDocument,
    StructuredThesis,
)


class ContextProvider(Protocol):
    async def load_analysis_context(
        self, portfolio_id: str, holding_id: str
    ) -> AnalysisContext: ...


class ResearchTools(Protocol):
    """B implements these methods with MCP tools; C never calls data APIs directly."""

    async def get_filings(self, request: ResearchRequest) -> list[SourceDocument]: ...

    async def get_news(self, request: ResearchRequest) -> list[SourceDocument]: ...

    async def get_macro(self, request: ResearchRequest) -> list[SourceDocument]: ...


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

    async def analyze_concentration(
        self, portfolio_theses: list[PortfolioThesis]
    ) -> PortfolioAnalysis: ...
