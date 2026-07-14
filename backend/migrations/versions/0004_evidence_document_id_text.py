"""Widen evidence.document_id to TEXT — Google News RSS article URLs
(used as document_id for NEWS evidence) routinely exceed the old
VARCHAR(255) limit, which raised StringDataRightTruncationError on any
real analysis run that surfaced news evidence. Caught via real end-to-end
scheduler testing (evidence.published_at / alerts.sent_at's naive-vs-tz-aware
mismatch was also fixed in models.py, but those columns were already
TIMESTAMPTZ at the DB level — that fix is ORM-only, no migration needed).

Revision ID: 0004_evidence_document_id_text
Revises: 0003_analysis_schedules
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_evidence_document_id_text"
down_revision: str | None = "0003_analysis_schedules"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("evidence") as batch_op:
        batch_op.alter_column("document_id", type_=sa.Text(), existing_type=sa.String(255))


def downgrade() -> None:
    with op.batch_alter_table("evidence") as batch_op:
        batch_op.alter_column("document_id", type_=sa.String(255), existing_type=sa.Text())
