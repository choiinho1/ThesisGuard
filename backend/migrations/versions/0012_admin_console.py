"""Add admin console tables: user role, app settings, QA logs, eval scenarios/runs.

Revision ID: 0012_admin_console
Revises: 0011_center_confidence_scores
Create Date: 2026-07-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_admin_console"
down_revision: str | None = "0011_center_confidence_scores"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

user_role = postgresql.ENUM("user", "admin", name="user_role", create_type=False)
eval_run_status = postgresql.ENUM(
    "PENDING", "RUNNING", "SUCCEEDED", "FAILED", name="eval_run_status", create_type=False
)


def upgrade() -> None:
    user_role.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "users",
        sa.Column("role", user_role, nullable=False, server_default="user"),
    )

    op.create_table(
        "app_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(120), nullable=False, unique=True),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column(
            "updated_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_app_settings_key", "app_settings", ["key"])

    op.create_table(
        "qa_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "portfolio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("evidence_document_ids", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_qa_logs_user_id", "qa_logs", ["user_id"])
    op.create_index("ix_qa_logs_portfolio_id", "qa_logs", ["portfolio_id"])

    op.create_table(
        "eval_scenarios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("context_snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("expected_document_ids", postgresql.JSONB(), nullable=True),
        sa.Column("required_keywords", postgresql.JSONB(), nullable=True),
        sa.Column("forbidden_terms", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    eval_run_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "eval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scenario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_scenarios.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "triggered_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("settings_snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("metrics", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", eval_run_status, nullable=False, server_default="PENDING"),
        sa.Column("error_message", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_eval_runs_scenario_id", "eval_runs", ["scenario_id"])


def downgrade() -> None:
    op.drop_index("ix_eval_runs_scenario_id", table_name="eval_runs")
    op.drop_table("eval_runs")
    eval_run_status.drop(op.get_bind(), checkfirst=True)
    op.drop_table("eval_scenarios")
    op.drop_index("ix_qa_logs_portfolio_id", table_name="qa_logs")
    op.drop_index("ix_qa_logs_user_id", table_name="qa_logs")
    op.drop_table("qa_logs")
    op.drop_index("ix_app_settings_key", table_name="app_settings")
    op.drop_table("app_settings")
    op.drop_column("users", "role")
    user_role.drop(op.get_bind(), checkfirst=True)
