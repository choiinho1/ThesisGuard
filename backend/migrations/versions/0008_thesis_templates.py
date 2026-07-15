"""Persist the selected scoring template and its immutable snapshot on theses.

Revision ID: 0008_thesis_templates
Revises: 0007_evidence_saved_to_history
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_thesis_templates"
down_revision: str | None = "0007_evidence_saved_to_history"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "theses",
        sa.Column(
            "template_id",
            sa.String(length=50),
            nullable=False,
            server_default="GENERAL_FUNDAMENTAL",
        ),
    )
    op.add_column(
        "theses",
        sa.Column(
            "template_catalog_version",
            sa.String(length=20),
            nullable=False,
            server_default="1.0.0",
        ),
    )
    op.add_column(
        "theses",
        sa.Column(
            "template_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "theses",
        sa.Column(
            "assumption_bindings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "theses",
        sa.Column(
            "score_breakdown",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("theses", "score_breakdown")
    op.drop_column("theses", "assumption_bindings")
    op.drop_column("theses", "template_snapshot")
    op.drop_column("theses", "template_catalog_version")
    op.drop_column("theses", "template_id")
