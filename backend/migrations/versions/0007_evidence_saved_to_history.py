"""evidence.saved_to_history — HIGH/MEDIUM-impact evidence is now flagged as
"saved to history" automatically at analysis time (manual or scheduled
re-analysis), instead of requiring the user to click a save button. Also
toggleable afterwards via POST/DELETE /api/evidence/{id}/save.

Revision ID: 0007_evidence_saved_to_history
Revises: 0006_alert_is_scheduled
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_evidence_saved_to_history"
down_revision: str | None = "0006_alert_is_scheduled"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evidence",
        sa.Column("saved_to_history", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("evidence", "saved_to_history")
