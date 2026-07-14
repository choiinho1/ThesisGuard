"""merge scheduler and evidence versioning branches

Revision ID: 2550db18e1ad
Revises: 0004_evidence_document_id_text, 0004_analysis_result_version
Create Date: 2026-07-14 15:22:40.612202
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '2550db18e1ad'
down_revision: str | None = ('0004_evidence_document_id_text', '0004_analysis_result_version')
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
