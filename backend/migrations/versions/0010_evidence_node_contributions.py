"""Persist evidence-by-node scoring details and score attribution.

Revision ID: 0010_evidence_node_contributions
Revises: 0009_thesis_logic_graph
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_evidence_node_contributions"
down_revision: str | None = "0009_thesis_logic_graph"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evidence",
        sa.Column(
            "assumption_findings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "evidence",
        sa.Column("score_delta", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "evidence",
        sa.Column(
            "node_contributions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("evidence", "node_contributions")
    op.drop_column("evidence", "score_delta")
    op.drop_column("evidence", "assumption_findings")
