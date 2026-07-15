"""alerts.is_scheduled — distinguishes alerts raised by the automatic
(scheduled) re-analysis run from ones raised by a user manually clicking
"재분석". Only scheduled alerts should surface in the alert UI, since manual
runs are already watched and confirmed by the user who triggered them.

Revision ID: 0006_alert_is_scheduled
Revises: 2550db18e1ad
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_alert_is_scheduled"
down_revision: str | None = "2550db18e1ad"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "alerts",
        sa.Column("is_scheduled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("alerts", "is_scheduled")
