"""SQLAlchemy ORM models (B-owned).

Enums that are part of the A<->B<->C contract (ThesisStatus, AlertSeverity,
EvidenceClassification, EvidenceImpact, EvidenceSourceType, AnalysisType) are
imported directly from ``agents.models`` so the database can never drift from
the Pydantic contract C ships. ``TransactionType`` and ``AlertDelivery`` are
backend-only concerns and are defined locally.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time
from enum import StrEnum

from agents.models import (
    AlertSeverity,
    AnalysisType,
    EvidenceClassification,
    EvidenceImpact,
    EvidenceSourceType,
    ThesisStatus,
)
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.types import TypeDecorator

from thesisguard_backend.db import Base


class TransactionType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    REBALANCE = "REBALANCE"
    CASH_ADJUST = "CASH_ADJUST"


class AlertDelivery(StrEnum):
    IMMEDIATE = "IMMEDIATE"
    WEEKLY = "WEEKLY"
    NONE = "NONE"


class ScheduledRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class EvalRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class UTCDateTime(TypeDecorator[datetime]):
    """Persist UTC datetimes and restore SQLite's discarded timezone metadata."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, _dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, _dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _json_type():
    """Use JSONB on PostgreSQL and portable JSON for local SQLite."""

    return JSON().with_variant(JSONB(), "postgresql")


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
    role: Mapped[UserRole] = mapped_column(
        # values_callable: SAEnum defaults to storing the Python enum *member
        # name* ("USER"), but UserRole's values ("user") are lowercase and
        # the Postgres "user_role" type (migration 0012) was created with
        # those lowercase labels — store .value instead, matching every
        # other StrEnum column that already uses this pattern indirectly by
        # having name == value.
        SAEnum(UserRole, name="user_role", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        default=UserRole.USER,
        server_default=UserRole.USER.value,
        nullable=False,
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    portfolios: Mapped[list[Portfolio]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    alerts: Mapped[list[Alert]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    investment_purpose: Mapped[str | None] = mapped_column(Text)
    investment_horizon: Mapped[str | None] = mapped_column(String(60))
    cash_ratio: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    user: Mapped[User] = relationship(back_populates="portfolios")
    holdings: Mapped[list[Holding]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )
    transactions: Mapped[list[Transaction]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )


class Holding(Base):
    __tablename__ = "holdings"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "ticker", name="uq_holdings_portfolio_ticker"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(120))
    quantity: Mapped[float] = mapped_column(Float, default=0)
    avg_buy_price: Mapped[float] = mapped_column(Float, default=0)
    target_weight: Mapped[float] = mapped_column(Float, default=0)
    current_weight: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    portfolio: Mapped[Portfolio] = relationship(back_populates="holdings")
    thesis: Mapped[Thesis] = relationship(
        back_populates="holding", uselist=False, cascade="all, delete-orphan"
    )
    analysis_schedule: Mapped[AnalysisSchedule] = relationship(
        back_populates="holding", uselist=False, cascade="all, delete-orphan"
    )


class AnalysisSchedule(Base):
    __tablename__ = "analysis_schedules"

    id: Mapped[uuid.UUID] = _uuid_pk()
    holding_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("holdings.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    daily_time: Mapped[time] = mapped_column(nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Seoul", nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    # PostgreSQL preserves timezone metadata natively. SQLite drops it on
    # round-trip, so UTCDateTime restores UTC before scheduler comparisons.
    last_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    next_run_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, index=True
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    holding: Mapped[Holding] = relationship(back_populates="analysis_schedule")
    runs: Mapped[list[ScheduledAnalysisRun]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan"
    )


class ScheduledAnalysisRun(Base):
    __tablename__ = "scheduled_analysis_runs"
    __table_args__ = (
        UniqueConstraint("schedule_id", "scheduled_for", name="uq_scheduled_run_slot"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_schedules.id", ondelete="CASCADE"), nullable=False
    )
    holding_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("holdings.id", ondelete="CASCADE"), nullable=False
    )
    scheduled_for: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[ScheduledRunStatus] = mapped_column(
        SAEnum(ScheduledRunStatus, name="scheduled_run_status"),
        default=ScheduledRunStatus.PENDING,
        nullable=False,
    )
    thesis_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("thesis_versions.id", ondelete="SET NULL")
    )
    alert_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("alerts.id", ondelete="SET NULL"))
    email_sent: Mapped[bool] = mapped_column(default=False, nullable=False)
    retry_count: Mapped[int] = mapped_column(default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()

    schedule: Mapped[AnalysisSchedule] = relationship(back_populates="runs")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType, name="transaction_type"), nullable=False
    )
    before_snapshot: Mapped[dict] = mapped_column(_json_type(), default=dict)
    after_snapshot: Mapped[dict] = mapped_column(_json_type(), default=dict)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()

    portfolio: Mapped[Portfolio] = relationship(back_populates="transactions")


class Thesis(Base):
    __tablename__ = "theses"
    __table_args__ = (UniqueConstraint("holding_id", name="uq_theses_holding_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    holding_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("holdings.id", ondelete="CASCADE"), nullable=False
    )
    raw_input: Mapped[str] = mapped_column(Text, nullable=False)
    main_thesis: Mapped[str] = mapped_column(Text, nullable=False)
    key_assumptions: Mapped[list[str]] = mapped_column(_json_type(), default=list)
    positive_signals: Mapped[list[str]] = mapped_column(_json_type(), default=list)
    negative_signals: Mapped[list[str]] = mapped_column(_json_type(), default=list)
    key_risks: Mapped[list[str]] = mapped_column(_json_type(), default=list)
    template_id: Mapped[str] = mapped_column(
        String(50), default="GENERAL_FUNDAMENTAL", nullable=False
    )
    template_catalog_version: Mapped[str] = mapped_column(
        String(20), default="deprecated", nullable=False
    )
    template_snapshot: Mapped[dict] = mapped_column(_json_type(), default=dict, nullable=False)
    assumption_bindings: Mapped[list[dict]] = mapped_column(
        _json_type(), default=list, nullable=False
    )
    logic_graph: Mapped[dict] = mapped_column(_json_type(), default=dict, nullable=False)
    score_breakdown: Mapped[dict] = mapped_column(_json_type(), default=dict, nullable=False)
    confidence_score: Mapped[int] = mapped_column(SmallInteger, default=0)
    status: Mapped[ThesisStatus] = mapped_column(
        SAEnum(ThesisStatus, name="thesis_status"), default=ThesisStatus.UNCHANGED, nullable=False
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    holding: Mapped[Holding] = relationship(back_populates="thesis")
    versions: Mapped[list[ThesisVersion]] = relationship(
        back_populates="thesis", cascade="all, delete-orphan", order_by="ThesisVersion.version_no"
    )
    evidence: Mapped[list[Evidence]] = relationship(
        back_populates="thesis", cascade="all, delete-orphan"
    )


class ThesisVersion(Base):
    __tablename__ = "thesis_versions"
    __table_args__ = (
        UniqueConstraint("thesis_id", "version_no", name="uq_thesis_versions_thesis_version"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    thesis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("theses.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(nullable=False)
    confidence_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[ThesisStatus] = mapped_column(
        SAEnum(ThesisStatus, name="thesis_status"), nullable=False
    )
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    conflicting_assumptions: Mapped[list[str]] = mapped_column(_json_type(), default=list)
    observation_points: Mapped[list[str]] = mapped_column(_json_type(), default=list)
    snapshot: Mapped[dict] = mapped_column(_json_type(), default=dict)
    created_at: Mapped[datetime] = _created_at()

    thesis: Mapped[Thesis] = relationship(back_populates="versions")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = _uuid_pk()
    thesis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("theses.id", ondelete="CASCADE"), nullable=False
    )
    # Nullable: only set for evidence created alongside a ThesisVersion (i.e.
    # every /analyze run going forward), so "give me the evidence for the
    # latest analysis" can filter on it instead of returning everything ever
    # collected for the thesis. Rows from before this column existed stay NULL.
    thesis_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("thesis_versions.id", ondelete="SET NULL"), index=True
    )
    # Text, not String(255): Google News RSS article URLs (used as document_id
    # for NEWS evidence) routinely exceed 255 chars.
    document_id: Mapped[str] = mapped_column(Text, nullable=False)
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
    related_assumptions: Mapped[list[str]] = mapped_column(_json_type(), default=list)
    assumption_findings: Mapped[list[dict]] = mapped_column(
        _json_type(), default=list, nullable=False
    )
    score_delta: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    node_contributions: Mapped[list[dict]] = mapped_column(
        _json_type(), default=list, nullable=False
    )
    # DateTime(timezone=True): agent-supplied values (SEC filing/news pubDate)
    # are tz-aware; the naive-inferred default made asyncpg reject inserts.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set automatically at analysis time for HIGH/MEDIUM impact evidence (see
    # routers/analysis.py's run_analysis_and_save), and toggleable afterwards
    # via POST/DELETE /api/evidence/{id}/save for LOW-impact evidence the user
    # wants to keep anyway. Backs the "주요 근거 History" view.
    saved_to_history: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = _created_at()

    thesis: Mapped[Thesis] = relationship(back_populates="evidence")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[uuid.UUID] = _uuid_pk()
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE")
    )
    thesis_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("theses.id", ondelete="CASCADE"))
    # Only set for BULL_BEAR_JUDGE rows (one per holding per analysis run);
    # THESIS_CONCENTRATION/COMMON_RISK rows are portfolio-wide and have no
    # single thesis version to attach to, so they stay NULL here too.
    thesis_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("thesis_versions.id", ondelete="SET NULL"), index=True
    )
    analysis_type: Mapped[AnalysisType] = mapped_column(
        SAEnum(AnalysisType, name="analysis_type"), nullable=False
    )
    bull_summary: Mapped[str | None] = mapped_column(Text)
    bear_summary: Mapped[str | None] = mapped_column(Text)
    judge_summary: Mapped[str | None] = mapped_column(Text)
    concentration_theme: Mapped[str | None] = mapped_column(String(255))
    concentration_score: Mapped[float | None] = mapped_column(Float)
    affected_holdings: Mapped[list[str]] = mapped_column(_json_type(), default=list)
    raw_result: Mapped[dict] = mapped_column(_json_type(), default=dict)
    created_at: Mapped[datetime] = _created_at()


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    thesis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("theses.id", ondelete="SET NULL")
    )
    severity: Mapped[AlertSeverity] = mapped_column(
        SAEnum(AlertSeverity, name="alert_severity"), nullable=False
    )
    delivery: Mapped[AlertDelivery] = mapped_column(
        SAEnum(AlertDelivery, name="alert_delivery"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_sent: Mapped[bool] = mapped_column(default=False, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # True only for alerts raised by the scheduled (automatic) re-analysis run —
    # manual "재분석" clicks still create/email an alert but are excluded from
    # the alert UI, since the user already watched that run and saw its result.
    is_scheduled: Mapped[bool] = mapped_column(default=False, nullable=False)
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


class AppSetting(Base):
    """Admin-tunable runtime parameter (key/value), read by settings_service.

    Lets scoring/alert/scheduler/LLM/RAG constants be changed from the admin
    UI without a redeploy. Rows are seeded from the hardcoded defaults on
    startup (see settings_service.seed_default_settings) and overridden here.
    """

    __tablename__ = "app_settings"

    id: Mapped[uuid.UUID] = _uuid_pk()
    key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[dict] = mapped_column(_json_type(), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class QaLog(Base):
    """Every portfolio Q&A question/answer pair, for later training use."""

    __tablename__ = "qa_logs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_document_ids: Mapped[list[str]] = mapped_column(_json_type(), default=list)
    created_at: Mapped[datetime] = _created_at()


class EvalScenario(Base):
    """Admin-curated regression scenario, mirrors agents/evaluation/datasets/*.json."""

    __tablename__ = "eval_scenarios"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    context_snapshot: Mapped[dict] = mapped_column(_json_type(), default=dict, nullable=False)
    expected_document_ids: Mapped[list[str]] = mapped_column(_json_type(), default=list)
    required_keywords: Mapped[list[str]] = mapped_column(_json_type(), default=list)
    forbidden_terms: Mapped[list[str]] = mapped_column(_json_type(), default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    runs: Mapped[list[EvalRun]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )


class EvalRun(Base):
    """Result of running one (or all) EvalScenario against current AppSettings."""

    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("eval_scenarios.id", ondelete="CASCADE"), index=True
    )
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    settings_snapshot: Mapped[dict] = mapped_column(_json_type(), default=dict, nullable=False)
    metrics: Mapped[dict] = mapped_column(_json_type(), default=dict, nullable=False)
    status: Mapped[EvalRunStatus] = mapped_column(
        SAEnum(EvalRunStatus, name="eval_run_status"),
        default=EvalRunStatus.PENDING,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()

    scenario: Mapped[EvalScenario | None] = relationship(back_populates="runs")
