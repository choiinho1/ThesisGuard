"""Pydantic request/response models for the API layer."""
import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class HoldingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    quantity: float
    avg_price: float
    target_weight: float
    latest_confidence: Optional[int] = None
    latest_status: Optional[str] = None
    has_thesis: bool = False


class PortfolioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    cash_ratio: float
    holdings: list[HoldingOut] = []


class ThesisCreateIn(BaseModel):
    raw_text: str


class ThesisVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    confidence_score: int
    status: str
    reason: dict
    timestamp: datetime.datetime


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: Optional[str]
    source_text: str
    related_premise: Optional[str]
    classification: str
    impact: str
    reasoning: str
    created_at: datetime.datetime


class ThesisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    holding_id: int
    raw_text: str
    main_thesis: str
    key_premises: list[str]
    risks: list[str]
    versions: list[ThesisVersionOut] = []
    evidence: list[EvidenceOut] = []


class AnalyzeResultOut(BaseModel):
    ticker: str
    previous_confidence: int
    new_confidence: int
    previous_status: str
    new_status: str
    what_changed: str
    conflicting_premises: list[str]
    overall_judgment: str
    watch_points: list[str]
    bull_argument: str
    bear_argument: str
    evidence: list[EvidenceOut]


# --- Portfolio Recommendation ---

class RecommendationIn(BaseModel):
    goal_text: str


class RecommendationHoldingOut(BaseModel):
    ticker: str
    weight: float
    reason: str


class RecommendationOut(BaseModel):
    portfolio_id: int
    strategy_summary: str
    holdings: list[RecommendationHoldingOut]
    cash_ratio: float
    knowledge_cutoff_caveat: str


# --- Arbitrary Portfolio Reality Check (no persistence) ---

class PortfolioCheckHoldingIn(BaseModel):
    ticker: str
    weight: float


class PortfolioCheckIn(BaseModel):
    label: Optional[str] = None
    holdings: list[PortfolioCheckHoldingIn]


class PortfolioCheckHoldingOut(BaseModel):
    ticker: str
    weight: float
    main_thesis: str
    key_premises: list[str]
    risks: list[str]
    reality_status: str
    confidence_score: int
    reasoning: str
    caveats: str


class PortfolioCheckOut(BaseModel):
    label: Optional[str] = None
    holdings: list[PortfolioCheckHoldingOut]
