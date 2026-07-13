"""initial schema — users/portfolios/holdings/transactions/theses/thesis_versions/evidence/analysis_results/alerts

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

thesis_status = postgresql.ENUM(
    "STRONGLY_STRENGTHENED",
    "STRENGTHENED",
    "UNCHANGED",
    "WEAKENED",
    "STRONGLY_WEAKENED",
    "BROKEN",
    name="thesis_status",
)
alert_severity = postgresql.ENUM("CRITICAL", "MAJOR", "MINOR", "NONE", name="alert_severity")
alert_delivery = postgresql.ENUM("IMMEDIATE", "WEEKLY", "NONE", name="alert_delivery")
evidence_classification = postgresql.ENUM(
    "SUPPORT", "CONTRADICT", "NEUTRAL", "UNCERTAIN", name="evidence_classification"
)
evidence_impact = postgresql.ENUM("HIGH", "MEDIUM", "LOW", name="evidence_impact")
evidence_source_type = postgresql.ENUM(
    "SEC_FILING", "IR", "EARNINGS", "NEWS", "MACRO", name="evidence_source_type"
)
transaction_type = postgresql.ENUM(
    "BUY", "SELL", "REBALANCE", "CASH_ADJUST", name="transaction_type"
)
analysis_type = postgresql.ENUM(
    "BULL_BEAR_JUDGE", "THESIS_CONCENTRATION", "COMMON_RISK", name="analysis_type"
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in (
        thesis_status,
        alert_severity,
        alert_delivery,
        evidence_classification,
        evidence_impact,
        evidence_source_type,
        transaction_type,
        analysis_type,
    ):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(120)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "portfolios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("investment_purpose", sa.Text()),
        sa.Column("investment_horizon", sa.String(60)),
        sa.Column("cash_ratio", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "holdings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ticker", sa.String(10), nullable=False),
        sa.Column("company_name", sa.String(120)),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_buy_price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("target_weight", sa.Float(), nullable=False, server_default="0"),
        sa.Column("current_weight", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", transaction_type, nullable=False),
        sa.Column("before_snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("after_snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "theses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("holding_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("holdings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_input", sa.Text(), nullable=False),
        sa.Column("main_thesis", sa.Text(), nullable=False),
        sa.Column("key_assumptions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("positive_signals", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("negative_signals", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("key_risks", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("confidence_score", sa.SmallInteger(), nullable=False, server_default="50"),
        sa.Column("status", thesis_status, nullable=False, server_default="UNCHANGED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("holding_id", name="uq_theses_holding_id"),
    )

    op.create_table(
        "thesis_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("thesis_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("theses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("confidence_score", sa.SmallInteger(), nullable=False),
        sa.Column("status", thesis_status, nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("conflicting_assumptions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("observation_points", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("thesis_id", "version_no", name="uq_thesis_versions_thesis_version"),
    )

    op.create_table(
        "evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("thesis_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("theses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.String(255), nullable=False),
        sa.Column("source_type", evidence_source_type, nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("vector_doc_id", sa.String(255)),
        sa.Column("content_snippet", sa.Text(), nullable=False),
        sa.Column("classification", evidence_classification, nullable=False),
        sa.Column("impact", evidence_impact, nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("related_assumptions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "analysis_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("portfolios.id", ondelete="CASCADE")),
        sa.Column("thesis_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("theses.id", ondelete="CASCADE")),
        sa.Column("analysis_type", analysis_type, nullable=False),
        sa.Column("bull_summary", sa.Text()),
        sa.Column("bear_summary", sa.Text()),
        sa.Column("judge_summary", sa.Text()),
        sa.Column("concentration_theme", sa.String(255)),
        sa.Column("concentration_score", sa.Float()),
        sa.Column("affected_holdings", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("raw_result", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("thesis_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("theses.id", ondelete="SET NULL")),
        sa.Column("severity", alert_severity, nullable=False),
        sa.Column("delivery", alert_delivery, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "alert_settings",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("immediate_alerts_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("weekly_digest_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("alert_settings")
    op.drop_table("alerts")
    op.drop_table("analysis_results")
    op.drop_table("evidence")
    op.drop_table("thesis_versions")
    op.drop_table("theses")
    op.drop_table("transactions")
    op.drop_table("holdings")
    op.drop_table("portfolios")
    op.drop_table("users")

    bind = op.get_bind()
    for enum_type in (
        analysis_type,
        transaction_type,
        evidence_source_type,
        evidence_impact,
        evidence_classification,
        alert_delivery,
        alert_severity,
        thesis_status,
    ):
        enum_type.drop(bind, checkfirst=True)
