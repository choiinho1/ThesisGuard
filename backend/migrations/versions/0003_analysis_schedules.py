"""Add daily analysis schedules and execution history.

Revision ID: 0003_analysis_schedules
Revises: 0002_unique_holding_ticker
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_analysis_schedules"
down_revision: str | None = "0002_unique_holding_ticker"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

run_status = postgresql.ENUM(
    "PENDING",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "SKIPPED",
    name="scheduled_run_status",
    create_type=False,
)


def upgrade() -> None:
    run_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "analysis_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "holding_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("holdings.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("daily_time", sa.Time(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Seoul"),
        sa.Column("recipient_email", sa.String(255), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_analysis_schedules_next_run_at", "analysis_schedules", ["next_run_at"])
    op.create_table(
        "scheduled_analysis_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "schedule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_schedules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "holding_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("holdings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", run_status, nullable=False),
        sa.Column(
            "thesis_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("thesis_versions.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "alert_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("alerts.id", ondelete="SET NULL"),
        ),
        sa.Column("email_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("schedule_id", "scheduled_for", name="uq_scheduled_run_slot"),
    )


def downgrade() -> None:
    op.drop_table("scheduled_analysis_runs")
    op.drop_index("ix_analysis_schedules_next_run_at", table_name="analysis_schedules")
    op.drop_table("analysis_schedules")
    run_status.drop(op.get_bind(), checkfirst=True)
