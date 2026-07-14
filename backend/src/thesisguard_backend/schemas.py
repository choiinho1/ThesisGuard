"""Pydantic request/response DTOs for the REST API (A<->B contract).

All field names are snake_case per the team naming convention, so the
frontend can consume these bodies without any key transformation. Response
shapes here are aligned 1:1 with frontend/types/schema.ts (branch
feature/fe-schema-alignment) — keep the two in sync when either changes.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from agents.models import (
    AlertSeverity,
    AnalysisType,
    EvidenceClassification,
    EvidenceImpact,
    EvidenceSourceType,
    ThesisStatus,
)
from thesisguard_backend.models import AlertDelivery, TransactionType


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- Auth ----
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleLoginRequest(BaseModel):
    id_token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(ORMModel):
    id: uuid.UUID
    email: EmailStr
    name: str | None
    created_at: datetime


# --------------------------------------------------------- Portfolio ----
class PortfolioCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    investment_purpose: str | None = None
    investment_horizon: str | None = None
    cash_ratio: float = Field(default=0, ge=0, le=100)


class PortfolioUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    investment_purpose: str | None = None
    investment_horizon: str | None = None
    cash_ratio: float | None = Field(default=None, ge=0, le=100)


class PortfolioResponse(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    investment_purpose: str | None
    investment_horizon: str | None
    cash_ratio: float
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------------------- Holding ----
class HoldingCreateRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    company_name: str | None = None
    quantity: float = Field(ge=0)
    avg_buy_price: float = Field(ge=0)
    target_weight: float = Field(default=0, ge=0, le=100)


class HoldingUpdateRequest(BaseModel):
    quantity: float | None = Field(default=None, ge=0)
    avg_buy_price: float | None = Field(default=None, ge=0)
    target_weight: float | None = Field(default=None, ge=0, le=100)
    current_weight: float | None = Field(default=None, ge=0, le=100)


class HoldingResponse(ORMModel):
    id: uuid.UUID
    portfolio_id: uuid.UUID
    ticker: str
    company_name: str | None
    quantity: float
    avg_buy_price: float
    target_weight: float
    current_weight: float
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------- Rebalancing ----
class RebalanceHoldingInput(BaseModel):
    holding_id: uuid.UUID
    quantity: float = Field(ge=0)
    target_weight: float = Field(ge=0, le=100)


class RebalanceRequest(BaseModel):
    holdings: list[RebalanceHoldingInput] = Field(min_length=1)
    cash_ratio: float = Field(ge=0, le=100)
    note: str | None = None


class TransactionResponse(ORMModel):
    id: uuid.UUID
    portfolio_id: uuid.UUID
    type: TransactionType
    before_snapshot: dict
    after_snapshot: dict
    note: str | None
    created_at: datetime


# ------------------------------------------------------------ Thesis ----
class ThesisCreateRequest(BaseModel):
    raw_input: str = Field(min_length=10)


class ThesisUpdateRequest(BaseModel):
    raw_input: str | None = Field(default=None, min_length=10)
    main_thesis: str | None = Field(default=None, min_length=5)
    key_assumptions: list[str] | None = None
    positive_signals: list[str] | None = None
    negative_signals: list[str] | None = None
    key_risks: list[str] | None = None


class ThesisResponse(ORMModel):
    id: uuid.UUID
    holding_id: uuid.UUID
    raw_input: str
    main_thesis: str
    key_assumptions: list[str]
    positive_signals: list[str]
    negative_signals: list[str]
    key_risks: list[str]
    confidence_score: int
    status: ThesisStatus
    created_at: datetime
    updated_at: datetime


class ThesisVersionResponse(ORMModel):
    id: uuid.UUID
    thesis_id: uuid.UUID
    version_no: int
    confidence_score: int
    status: ThesisStatus
    change_reason: str
    conflicting_assumptions: list[str]
    observation_points: list[str]
    snapshot: dict
    created_at: datetime


# ---------------------------------------------------------- Evidence ----
class EvidenceResponse(ORMModel):
    id: uuid.UUID
    thesis_id: uuid.UUID
    document_id: str
    source_type: EvidenceSourceType
    source_url: str | None
    vector_doc_id: str | None
    content_snippet: str
    classification: EvidenceClassification
    impact: EvidenceImpact
    reason: str
    related_assumptions: list[str]
    published_at: datetime | None


# ------------------------------------------------- Analysis / Concentration
class AnalysisResultResponse(ORMModel):
    id: uuid.UUID
    portfolio_id: uuid.UUID | None
    thesis_id: uuid.UUID | None
    analysis_type: AnalysisType
    bull_summary: str | None
    bear_summary: str | None
    judge_summary: str | None
    concentration_theme: str | None
    concentration_score: float | None
    affected_holdings: list[str]
    raw_result: dict
    created_at: datetime


class NaturalLanguageQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class NaturalLanguageQueryResponse(BaseModel):
    answer: str
    evidence_document_ids: list[str]
    limitations: list[str]


# ------------------------------------------------------------- Alert ----
class AlertResponse(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    portfolio_id: uuid.UUID
    thesis_id: uuid.UUID | None
    severity: AlertSeverity
    delivery: AlertDelivery
    title: str
    message: str
    is_sent: bool
    sent_at: datetime | None
    created_at: datetime


class AlertSettingsRequest(BaseModel):
    immediate_alerts_enabled: bool
    weekly_digest_enabled: bool


class AlertSettingsResponse(ORMModel):
    user_id: uuid.UUID
    immediate_alerts_enabled: bool
    weekly_digest_enabled: bool
    updated_at: datetime


# ---------------------------------------------------- Composite responses
# These mirror frontend/types/schema.ts's DashboardHolding, PortfolioDashboard
# and HoldingAnalysisResponse exactly (field-for-field, including key names
# like "version" instead of "thesis_version").


class DashboardHoldingResponse(HoldingResponse):
    thesis: ThesisResponse | None = None
    latest_change: ThesisVersionResponse | None = None


class PortfolioDashboardResponse(BaseModel):
    portfolio: PortfolioResponse
    holdings: list[DashboardHoldingResponse]
    concentration: AnalysisResultResponse | None
    common_risks: list[AnalysisResultResponse]
    recent_alerts: list[AlertResponse]


class HoldingAnalysisResponse(BaseModel):
    thesis: ThesisResponse
    version: ThesisVersionResponse
    evidence: list[EvidenceResponse]
    analysis_result: AnalysisResultResponse
    alert: AlertResponse | None
