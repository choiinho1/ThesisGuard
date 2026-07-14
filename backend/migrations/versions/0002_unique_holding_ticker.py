"""Prevent duplicate tickers within the same portfolio.

Revision ID: 0002_unique_holding_ticker
Revises: 0001_initial_schema
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_unique_holding_ticker"
down_revision: str | None = "0001_initial_schema"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

CONSTRAINT_NAME = "uq_holdings_portfolio_ticker"


def upgrade() -> None:
    bind = op.get_bind()
    duplicate = bind.execute(
        sa.text(
            """
            SELECT portfolio_id, UPPER(TRIM(ticker)) AS normalized_ticker, COUNT(*) AS count
            FROM holdings
            GROUP BY portfolio_id, UPPER(TRIM(ticker))
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "중복 보유 종목을 먼저 정리해야 합니다: "
            f"portfolio_id={duplicate.portfolio_id}, "
            f"ticker={duplicate.normalized_ticker}, count={duplicate.count}"
        )

    op.execute(sa.text("UPDATE holdings SET ticker = UPPER(TRIM(ticker))"))
    with op.batch_alter_table("holdings") as batch_op:
        batch_op.create_unique_constraint(CONSTRAINT_NAME, ["portfolio_id", "ticker"])


def downgrade() -> None:
    with op.batch_alter_table("holdings") as batch_op:
        batch_op.drop_constraint(CONSTRAINT_NAME, type_="unique")
