"""evidence: widen document_id to TEXT, link evidence to the thesis_version
it was collected for.

Widening: Google News RSS article URLs (used as document_id for NEWS
evidence) routinely exceed the old VARCHAR(255) limit, which raised
StringDataRightTruncationError on any real analysis run that surfaced
news evidence.

Linking: without thesis_version_id, "give me the evidence for the most
recent analysis" had no way to distinguish evidence from an old run vs the
current one — evidence only ever accumulates per thesis. New rows going
forward set thesis_version_id at insert time; existing rows stay NULL.

Revision ID: 0003_evidence_versioning
Revises: 0002_unique_holding_ticker
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_evidence_versioning"
down_revision: str | None = "0002_unique_holding_ticker"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("evidence") as batch_op:
        batch_op.alter_column("document_id", type_=sa.Text(), existing_type=sa.String(255))
        batch_op.add_column(
            sa.Column(
                "thesis_version_id",
                sa.Uuid(as_uuid=True),
                sa.ForeignKey("thesis_versions.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
    op.create_index(
        "ix_evidence_thesis_version_id", "evidence", ["thesis_version_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_thesis_version_id", table_name="evidence")
    with op.batch_alter_table("evidence") as batch_op:
        batch_op.drop_column("thesis_version_id")
        batch_op.alter_column(
            "document_id", type_=sa.String(255), existing_type=sa.Text()
        )
