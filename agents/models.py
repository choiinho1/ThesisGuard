"""B(Backend) and C(AI Agent) shared Pydantic contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)


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


class EvidenceImpact(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EvidenceSourceType(StrEnum):
    SEC_FILING = "SEC_FILING"
    IR = "IR"
    EARNINGS = "EARNINGS"
    NEWS = "NEWS"
    MACRO = "MACRO"


class AlertSeverity(StrEnum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    NONE = "NONE"


class AnalysisType(StrEnum):
    BULL_BEAR_JUDGE = "BULL_BEAR_JUDGE"
    THESIS_CONCENTRATION = "THESIS_CONCENTRATION"
    COMMON_RISK = "COMMON_RISK"


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
    ticker: str = Field(min_length=1, max_length=10)
    current_weight: float = Field(default=0, ge=0, le=100)
    thesis: StructuredThesis


class AnalysisContext(ContractModel):
    portfolio_id: str
    holding_id: str
    ticker: str = Field(min_length=1, max_length=10)
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
    source_type: EvidenceSourceType
    source_url: HttpUrl | None = None
    vector_doc_id: str | None = None
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    published_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceItem(ContractModel):
    document_id: str
    source_type: EvidenceSourceType
    source_url: HttpUrl | None = None
    vector_doc_id: str | None = None
    content_snippet: str = Field(min_length=1, max_length=2000)
    classification: EvidenceClassification
    impact: EvidenceImpact
    reason: str = Field(min_length=1)
    related_assumptions: list[str] = Field(default_factory=list)
    published_at: datetime | None = None

    @model_validator(mode="after")
    def require_reference_for_directional_evidence(self) -> EvidenceItem:
        directional = self.classification in {
            EvidenceClassification.SUPPORT,
            EvidenceClassification.CONTRADICT,
        }
        if directional and self.source_url is None and self.vector_doc_id is None:
            raise ValueError("Directional evidence must reference a URL or vector document")
        return self


class EvidenceAssessment(ContractModel):
    classification: EvidenceClassification
    impact: EvidenceImpact
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


class CommonRisk(ContractModel):
    risk: str = Field(min_length=1)
    affected_holdings: list[str] = Field(default_factory=list)
    evidence_document_ids: list[str] = Field(default_factory=list)


class PortfolioAnalysis(ContractModel):
    themes: list[ConcentrationTheme] = Field(default_factory=list)
    common_risks: list[CommonRisk] = Field(default_factory=list)
    has_concentration_risk: bool = False
    summary: str = "집중 테마 없음"


class PortfolioQueryAnswer(ContractModel):
    answer: str = Field(min_length=1)
    evidence_document_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


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
