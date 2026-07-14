"""analysis_results.thesis_version_id — link each BULL_BEAR_JUDGE row to the
analysis run (ThesisVersion) it belongs to, mirroring evidence's
thesis_version_id from 0003. Needed for the upcoming per-holding history
endpoint to match each timeline entry's bull/bear/judge summary to its
version without guessing by created_at proximity.

Revision ID: 0004_analysis_result_version
Revises: 0003_evidence_versioning
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_analysis_result_version"
down_revision: str | None = "0003_evidence_versioning"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analysis_results",
        sa.Column(
            "thesis_version_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("thesis_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_analysis_results_thesis_version_id", "analysis_results", ["thesis_version_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_results_thesis_version_id", table_name="analysis_results")
    op.drop_column("analysis_results", "thesis_version_id")
