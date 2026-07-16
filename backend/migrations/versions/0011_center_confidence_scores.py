"""Center thesis confidence scores on zero with a -50 to 50 range.

Revision ID: 0011_center_confidence_scores
Revises: 0010_evidence_node_contributions
Create Date: 2026-07-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_center_confidence_scores"
down_revision: str | None = "0010_evidence_node_contributions"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _shift_json_score(path: str, *, delta: int, table: str, column: str) -> None:
    key_path = "{" + path.replace(".", ",") + "}"
    json_path = path.split(".")
    lookup = " #> " + repr("{" + ",".join(json_path) + "}")
    text_lookup = " #>> " + repr("{" + ",".join(json_path) + "}")
    op.execute(
        sa.text(
            f"""
            UPDATE {table}
            SET {column} = jsonb_set(
                {column},
                '{key_path}',
                to_jsonb((({column}{text_lookup})::integer + :delta)),
                false
            )
            WHERE jsonb_typeof({column}{lookup}) = 'number'
            """
        ).bindparams(delta=delta)
    )


def _shift_scores(delta: int) -> None:
    op.execute(
        sa.text(
            "UPDATE theses SET confidence_score = confidence_score + :delta"
        ).bindparams(delta=delta)
    )
    op.execute(
        sa.text(
            "UPDATE thesis_versions SET confidence_score = confidence_score + :delta"
        ).bindparams(delta=delta)
    )

    for path in ("previous_score", "health_score"):
        _shift_json_score(path, delta=delta, table="theses", column="score_breakdown")
        _shift_json_score(
            f"score_breakdown.{path}",
            delta=delta,
            table="thesis_versions",
            column="snapshot",
        )
        _shift_json_score(
            f"score_breakdown.{path}",
            delta=delta,
            table="analysis_results",
            column="raw_result",
        )

    _shift_json_score(
        "confidence_score",
        delta=delta,
        table="thesis_versions",
        column="snapshot",
    )
    _shift_json_score(
        "updated_confidence",
        delta=delta,
        table="analysis_results",
        column="raw_result",
    )


def upgrade() -> None:
    _shift_scores(-50)
    op.alter_column("theses", "confidence_score", server_default=sa.text("0"))


def downgrade() -> None:
    _shift_scores(50)
    op.alter_column("theses", "confidence_score", server_default=sa.text("50"))
