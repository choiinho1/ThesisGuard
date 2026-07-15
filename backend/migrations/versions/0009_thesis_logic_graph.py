"""Persist each thesis-specific causal logic graph.

Revision ID: 0009_thesis_logic_graph
Revises: 0008_thesis_templates
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_thesis_logic_graph"
down_revision: str | None = "0008_thesis_templates"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "theses",
        sa.Column(
            "logic_graph",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("theses", "logic_graph")
