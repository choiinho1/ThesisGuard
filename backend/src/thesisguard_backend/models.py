"""SQLAlchemy ORM models (B-owned).

Enums that are part of the A<->B<->C contract (ThesisStatus, AlertSeverity,
EvidenceClassification, EvidenceImpact, EvidenceSourceType, AnalysisType) are
imported directly from ``agents.models`` so the database can never drift from
the Pydantic contract C ships. ``TransactionType`` and ``AlertDelivery`` are
backend-only concerns and are defined locally.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, ForeignKey, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from agents.models import (
    AlertSeverity,
    AnalysisType,
    EvidenceClassification,
    EvidenceImpact,
    EvidenceSourceType,
    ThesisStatus,
)
from thesisguard_backend.db import Base


class TransactionType(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    REBALANCE = "REBALANCE"
    CASH_ADJUST = "CASH_ADJUST"


class AlertDelivery(str, enum.Enum):
    IMMEDIATE = "IMMEDIATE"
    WEEKLY = "WEEKLY"
    NONE = "NONE"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(server_default=func.now(), nullable=False)


def _updated_at() -> Mapped[datetime]:
    return mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    portfolios: Mapped[list["Portfolio"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    investment_purpose: Mapped[str | None] = mapped_column(Text)
    investment_horizon: Mapped[str | None] = mapped_column(String(60))
    cash_ratio: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    user: Mapped[User] = relationship(back_populates="portfolios")
    holdings: Mapped[list["Holding"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[uuid.UUID] = _uuid_pk()
    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(120))
    quantity: Mapped[float] = mapped_column(Float, default=0)
    avg_buy_price: Mapped[float] = mapped_column(Float, default=0)
    target_weight: Mapped[float] = mapped_column(Float, default=0)
    current_weight: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    portfolio: Mapped[Portfolio] = relationship(back_populates="holdings")
    thesis: Mapped["Thesis"] = relationship(back_populates="holding", uselist=False, cascade="all, delete-orphan")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[TransactionType] = mapped_column(SAEnum(TransactionType, name="transaction_type"), nullable=False)
    before_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    after_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()

    portfolio: Mapped[Portfolio] = relationship(back_populates="transactions")


class Thesis(Base):
    __tablename__ = "theses"
    __table_args__ = (UniqueConstraint("holding_id", name="uq_theses_holding_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    holding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("holdings.id", ondelete="CASCADE"), nullable=False)
    raw_input: Mapped[str] = mapped_column(Text, nullable=False)
    main_thesis: Mapped[str] = mapped_column(Text, nullable=False)
    key_assumptions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    positive_signals: Mapped[list[str]] = mapped_column(JSONB, default=list)
    negative_signals: Mapped[list[str]] = mapped_column(JSONB, default=list)
    key_risks: Mapped[list[str]] = mapped_column(JSONB, default=list)
    confidence_score: Mapped[int] = mapped_column(SmallInteger, default=50)
    status: Mapped[ThesisStatus] = mapped_column(
        SAEnum(ThesisStatus, name="thesis_status"), default=ThesisStatus.UNCHANGED, nullable=False
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    holding: Mapped[Holding] = relationship(back_populates="thesis")
    versions: Mapped[list["ThesisVersion"]] = relationship(
        back_populates="thesis", cascade="all, delete-orphan", order_by="ThesisVersion.version_no"
    )
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="thesis", cascade="all, delete-orphan")


class ThesisVersion(Base):
    __tablename__ = "thesis_versions"
    __table_args__ = (UniqueConstraint("thesis_id", "version_no", name="uq_thesis_versions_thesis_version"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    thesis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("theses.id", ondelete="CASCADE"), nullable=False)
    version_no: Mapped[int] = mapped_column(nullable=False)
    confidence_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[ThesisStatus] = mapped_column(SAEnum(ThesisStatus, name="thesis_status"), nullable=False)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    conflicting_assumptions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    observation_points: Mapped[list[str]] = mapped_column(JSONB, default=list)
    snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _created_at()

    thesis: Mapped[Thesis] = relationship(back_populates="versions")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = _uuid_pk()
    thesis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("theses.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[EvidenceSourceType] = mapped_column(
        SAEnum(EvidenceSourceType, name="evidence_source_type"), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    vector_doc_id: Mapped[str | None] = mapped_column(String(255))
    content_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[EvidenceClassification] = mapped_column(
        SAEnum(EvidenceClassification, name="evidence_classification"), nullable=False
    )
    impact: Mapped[EvidenceImpact] = mapped_column(
        SAEnum(EvidenceImpact, name="evidence_impact"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    related_assumptions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    published_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = _created_at()

    thesis: Mapped[Thesis] = relationship(back_populates="evidence")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[uuid.UUID] = _uuid_pk()
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    thesis_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("theses.id", ondelete="CASCADE"))
    analysis_type: Mapped[AnalysisType] = mapped_column(SAEnum(AnalysisType, name="analysis_type"), nullable=False)
    bull_summary: Mapped[str | None] = mapped_column(Text)
    bear_summary: Mapped[str | None] = mapped_column(Text)
    judge_summary: Mapped[str | None] = mapped_column(Text)
    concentration_theme: Mapped[str | None] = mapped_column(String(255))
    concentration_score: Mapped[float | None] = mapped_column(Float)
    affected_holdings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    raw_result: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _created_at()


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    thesis_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("theses.id", ondelete="SET NULL"))
    severity: Mapped[AlertSeverity] = mapped_column(SAEnum(AlertSeverity, name="alert_severity"), nullable=False)
    delivery: Mapped[AlertDelivery] = mapped_column(SAEnum(AlertDelivery, name="alert_delivery"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_sent: Mapped[bool] = mapped_column(default=False, nullable=False)
    sent_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = _created_at()

    user: Mapped[User] = relationship(back_populates="alerts")


class AlertSettings(Base):
    """One row per user: how CRITICAL/MAJOR/MINOR alerts are delivered."""

    __tablename__ = "alert_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    immediate_alerts_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    weekly_digest_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    updated_at: Mapped[datetime] = _updated_at()
