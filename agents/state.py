"""LangGraph AnalysisState from the team contract."""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from agents.models import (
    AlertDecision,
    DebateReport,
    EvidenceItem,
    JudgeDecision,
    PortfolioAnalysis,
    PortfolioThesis,
    SourceDocument,
    StructuredThesis,
    ThesisAnalysisResult,
    ThesisStatus,
)


class ResearchData(TypedDict):
    filings: list[SourceDocument]
    news: list[SourceDocument]
    macro: list[SourceDocument]


def empty_research_data() -> ResearchData:
    return {"filings": [], "news": [], "macro": []}


def merge_research_data(left: ResearchData, right: ResearchData) -> ResearchData:
    return {
        "filings": [*left.get("filings", []), *right.get("filings", [])],
        "news": [*left.get("news", []), *right.get("news", [])],
        "macro": [*left.get("macro", []), *right.get("macro", [])],
    }


class AnalysisState(TypedDict, total=False):
    portfolio_id: str
    holding_id: str
    ticker: str
    thesis_snapshot: StructuredThesis
    research_data: Annotated[ResearchData, merge_research_data]
    selected_documents: list[SourceDocument]
    evidence_list: list[EvidenceItem]
    needs_more_research: bool
    bull_report: str
    bear_report: str
    judge_report: str
    updated_confidence: int
    updated_status: ThesisStatus
    change_reason: str
    conflicting_assumptions: list[str]
    observation_points: list[str]
    alert_decision: AlertDecision

    portfolio_theses: list[PortfolioThesis]
    research_round: int
    focus_points: list[str]
    source_errors: Annotated[list[str], operator.add]
    bull_evidence_document_ids: list[str]
    bear_evidence_document_ids: list[str]
    bull_report_data: DebateReport
    bear_report_data: DebateReport
    judge_decision: JudgeDecision
    portfolio_analysis: PortfolioAnalysis
    result: ThesisAnalysisResult
