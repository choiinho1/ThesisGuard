"""B(Backend) and C(AI Agent) shared Pydantic contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    NonNegativeInt,
    model_validator,
)


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


class AssumptionAssessment(StrEnum):
    SUPPORT = "SUPPORT"
    CONTRADICT = "CONTRADICT"
    MIXED = "MIXED"
    NOT_ADDRESSED = "NOT_ADDRESSED"


class AssumptionFinding(ContractModel):
    """How one document affects one exact thesis assumption."""

    assumption: str = Field(min_length=1)
    assessment: AssumptionAssessment
    impact: EvidenceImpact
    relevance_score: float = Field(ge=0, le=1)
    reasoning: str = Field(min_length=1)
    source_passage_indices: list[NonNegativeInt] = Field(default_factory=list, max_length=3)


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


class AssumptionBinding(ContractModel):
    """Deprecated template binding retained only for old serialized records."""

    slot_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    assumptions: list[str] = Field(default_factory=list)
    mapping_reason: str = ""


class LogicOperator(StrEnum):
    AND = "AND"
    OR = "OR"
    CONTRIBUTING = "CONTRIBUTING"


class ThesisLogicNode(ContractModel):
    """Potential model output; trusted code validates its semantic shape."""

    node_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    kind: Literal["CLAIM", "ASSUMPTION"]
    label: str = Field(min_length=1)
    operator: LogicOperator | None = None
    child_ids: list[str] = Field(default_factory=list)
    assumption: str | None = None


class ThesisLogicGraph(ContractModel):
    graph_version: str = "1.0.0"
    root_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    nodes: list[ThesisLogicNode] = Field(min_length=2)


class AssumptionScoreState(ContractModel):
    assumption: str = Field(min_length=1)
    node_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    support_strength: float = Field(default=0, ge=0, le=1)
    contradict_strength: float = Field(default=0, ge=0, le=1)
    state: float = Field(default=0, ge=-1, le=1)
    has_evidence: bool = False
    evidence_document_ids: list[str] = Field(default_factory=list)
    evidence_event_keys: list[str] = Field(default_factory=list)
    invalidation_streak: int = Field(default=0, ge=0)
    invalidation_triggered: bool = False


class LogicNodeScore(ContractModel):
    node_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    kind: Literal["CLAIM", "ASSUMPTION"]
    operator: LogicOperator | None = None
    state: float = Field(ge=-1, le=1)
    coverage_percent: float = Field(ge=0, le=100)
    required: bool = False


class EvidenceNodeContribution(ContractModel):
    """Deterministic signed strength of one evidence item against one leaf node."""

    node_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    assumption: str = Field(min_length=1)
    assessment: AssumptionAssessment
    impact: EvidenceImpact
    relevance_score: float = Field(ge=0, le=1)
    signed_strength: float = Field(ge=-1, le=1)


class EvidenceScoreImpact(ContractModel):
    """Attribution of the analysis score movement to one information item."""

    document_id: str = Field(min_length=1)
    score_delta: float = Field(ge=-100, le=100)
    node_contributions: list[EvidenceNodeContribution] = Field(default_factory=list)


class ThesisScoreBreakdown(ContractModel):
    scoring_method: Literal["EVIDENCE_NODE_MATRIX_V2"] = "EVIDENCE_NODE_MATRIX_V2"
    logic_graph_version: str = "1.0.0"
    previous_score: int = Field(ge=0, le=100)
    health_score: int = Field(ge=0, le=100)
    score_delta: int = Field(ge=-100, le=100)
    root_state: float = Field(ge=-1, le=1)
    coverage_percent: float = Field(ge=0, le=100)
    invalidation_policy_version: str = "1.0.0"
    is_broken: bool = False
    invalidated_assumptions: list[str] = Field(default_factory=list)
    assumption_scores: list[AssumptionScoreState] = Field(default_factory=list)
    node_scores: list[LogicNodeScore] = Field(default_factory=list)
    evidence_impacts: list[EvidenceScoreImpact] = Field(default_factory=list)


class StructuredThesis(ContractModel):
    raw_input: str = Field(min_length=10)
    main_thesis: str = Field(min_length=5)
    key_assumptions: list[str] = Field(min_length=1)
    positive_signals: list[str] = Field(default_factory=list)
    negative_signals: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    logic_graph: ThesisLogicGraph | None = None
    score_breakdown: ThesisScoreBreakdown | None = None
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
    evidence_history_summary: str = ""
    evidence_history_document_ids: list[str] = Field(default_factory=list)
    evidence_history_source_urls: list[str] = Field(default_factory=list)


class ResearchRequest(ContractModel):
    portfolio_id: str
    holding_id: str
    ticker: str
    thesis: StructuredThesis
    round_no: int = Field(ge=1)
    focus_points: list[str] = Field(default_factory=list)
    lookback_days: int = Field(default=30, ge=1, le=365)
    candidate_limit: int = Field(default=15, ge=1, le=50)


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
    content_snippet: str = Field(min_length=1, max_length=500)
    classification: EvidenceClassification
    impact: EvidenceImpact
    reason: str = Field(min_length=1)
    related_assumptions: list[str] = Field(default_factory=list)
    assumption_findings: list[AssumptionFinding] = Field(default_factory=list)
    published_at: datetime | None = None

    @model_validator(mode="after")
    def require_reference_for_directional_evidence(self) -> EvidenceItem:
        directional = self.classification in {
            EvidenceClassification.SUPPORT,
            EvidenceClassification.CONTRADICT,
        } or any(
            finding.assessment
            in {AssumptionAssessment.SUPPORT, AssumptionAssessment.CONTRADICT}
            for finding in self.assumption_findings
        )
        if directional and self.source_url is None and self.vector_doc_id is None:
            raise ValueError("Directional evidence must reference a URL or vector document")
        return self


class EvidenceAssessment(ContractModel):
    classification: EvidenceClassification
    impact: EvidenceImpact
    relevance_score: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)
    related_assumptions: list[str] = Field(default_factory=list)
    assumption_findings: list[AssumptionFinding] = Field(default_factory=list)
    source_excerpt: str = Field(min_length=1, max_length=2000)
    content_snippet: str = Field(min_length=1, max_length=500)


class EvidenceModelOutput(ContractModel):
    """Structured model output; the selected passage is resolved by trusted code."""

    classification: EvidenceClassification
    impact: EvidenceImpact
    relevance_score: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)
    related_assumptions: list[str] = Field(default_factory=list)
    assumption_findings: list[AssumptionFinding] = Field(default_factory=list)
    source_passage_indices: list[NonNegativeInt] = Field(min_length=1, max_length=3)
    content_snippet: str = Field(min_length=1, max_length=500)


class DebateReport(ContractModel):
    summary: str = Field(min_length=1)
    evidence_document_ids: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)


class JudgeExplanation(ContractModel):
    """Narrative-only judgment; deterministic code owns score and status."""

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
    score_breakdown: ThesisScoreBreakdown
    change_reason: str
    conflicting_assumptions: list[str] = Field(default_factory=list)
    observation_points: list[str] = Field(default_factory=list)
    concentration: PortfolioAnalysis
    alert_decision: AlertDecision
    research_rounds: int = Field(ge=1)
    source_errors: list[str] = Field(default_factory=list)
