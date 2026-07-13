"""Shared contracts between Backend(B) and AI Agent Core(C)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class ContractModel(BaseModel):
    """Strict base model used at team ownership boundaries."""

    model_config = ConfigDict(extra="forbid", use_enum_values=False)


class SourceType(StrEnum):
    FILING = "FILING"
    NEWS = "NEWS"
    MACRO = "MACRO"


class EvidenceClassification(StrEnum):
    SUPPORT = "SUPPORT"
    CONTRADICT = "CONTRADICT"
    NEUTRAL = "NEUTRAL"
    UNCERTAIN = "UNCERTAIN"


class ThesisStatus(StrEnum):
    STRONGLY_STRENGTHENED = "STRONGLY_STRENGTHENED"
    STRENGTHENED = "STRENGTHENED"
    UNCHANGED = "UNCHANGED"
    WEAKENED = "WEAKENED"
    STRONGLY_WEAKENED = "STRONGLY_WEAKENED"
    BROKEN = "BROKEN"


class AlertSeverity(StrEnum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    NONE = "NONE"


class StructuredThesis(ContractModel):
    raw_input: str = Field(min_length=10)
    main_thesis: str = Field(min_length=5)
    key_assumptions: list[str] = Field(min_length=1)
    positive_signals: list[str] = Field(default_factory=list)
    negative_signals: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    confidence_score: int = Field(default=50, ge=0, le=100)
    status: ThesisStatus = ThesisStatus.UNCHANGED


class PortfolioThesis(ContractModel):
    holding_id: str
    ticker: str = Field(min_length=1)
    current_weight: float = Field(default=0, ge=0, le=100)
    thesis: StructuredThesis


class AnalysisContext(ContractModel):
    portfolio_id: str
    holding_id: str
    ticker: str = Field(min_length=1)
    thesis: StructuredThesis
    portfolio_theses: list[PortfolioThesis] = Field(default_factory=list)


class ResearchRequest(ContractModel):
    portfolio_id: str
    holding_id: str
    ticker: str
    thesis: StructuredThesis
    round_no: int = Field(ge=1)
    focus_points: list[str] = Field(default_factory=list)


class SourceDocument(ContractModel):
    document_id: str
    source_type: SourceType
    source_url: HttpUrl
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    published_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceItem(ContractModel):
    document_id: str
    source_type: SourceType
    source_url: HttpUrl
    content_snippet: str = Field(min_length=1, max_length=2000)
    classification: EvidenceClassification
    impact: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)
    related_assumptions: list[str] = Field(default_factory=list)
    published_at: datetime | None = None

    @model_validator(mode="after")
    def require_grounded_directional_claim(self) -> EvidenceItem:
        if self.classification in {
            EvidenceClassification.SUPPORT,
            EvidenceClassification.CONTRADICT,
        }:
            if not self.content_snippet.strip() or not str(self.source_url):
                raise ValueError("Directional evidence must include a citation and snippet")
        return self


class EvidenceAssessment(ContractModel):
    classification: EvidenceClassification
    impact: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)
    related_assumptions: list[str] = Field(default_factory=list)
    content_snippet: str = Field(min_length=1, max_length=2000)


class DebateReport(ContractModel):
    summary: str = Field(min_length=1)
    evidence_document_ids: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)


class JudgeDecision(ContractModel):
    updated_confidence: int = Field(ge=0, le=100)
    updated_status: ThesisStatus
    change_reason: str = Field(min_length=1)
    judge_summary: str = Field(min_length=1)
    conflicting_assumptions: list[str] = Field(default_factory=list)
    observation_points: list[str] = Field(default_factory=list)


class ConcentrationTheme(ContractModel):
    theme: str = Field(min_length=1)
    concentration_score: float = Field(ge=0, le=100)
    affected_holdings: list[str] = Field(default_factory=list)
    shared_assumptions: list[str] = Field(default_factory=list)


class PortfolioAnalysis(ContractModel):
    themes: list[ConcentrationTheme] = Field(default_factory=list)
    has_concentration_risk: bool = False
    summary: str = "집중 테마 없음"


class AlertDecision(ContractModel):
    severity: AlertSeverity
    should_send: bool
    delivery: str = Field(pattern="^(IMMEDIATE|WEEKLY|NONE)$")
    reason: str


class ThesisAnalysisResult(ContractModel):
    portfolio_id: str
    holding_id: str
    ticker: str
    evidence: list[EvidenceItem]
    bull_summary: str
    bear_summary: str
    judge_summary: str
    updated_confidence: int = Field(ge=0, le=100)
    updated_status: ThesisStatus
    change_reason: str
    conflicting_assumptions: list[str] = Field(default_factory=list)
    observation_points: list[str] = Field(default_factory=list)
    concentration: PortfolioAnalysis
    alert_decision: AlertDecision
    research_rounds: int = Field(ge=1)
