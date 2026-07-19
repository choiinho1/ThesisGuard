"""Async SQLAlchemy engine/session setup."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event, inspect
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from thesisguard_backend.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


if engine.url.get_backend_name() == "sqlite":

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


async def initialize_local_database() -> None:
    """Create tables automatically for the zero-setup local SQLite database."""

    if engine.url.get_backend_name() != "sqlite":
        return

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(_upgrade_legacy_local_schema)


def _upgrade_legacy_local_schema(connection: Connection) -> None:
    """Add nullable columns introduced after an existing local DB was created.

    ``create_all`` creates missing tables but intentionally does not alter
    existing ones. Local SQLite installs do not have an Alembic version table,
    so keep this small compatibility bridge for additive, data-safe changes.
    Production databases continue to use Alembic migrations.
    """

    inspector = inspect(connection)
    additive_columns = {
        "evidence": (
            (
                "thesis_version_id",
                "ALTER TABLE evidence ADD COLUMN thesis_version_id CHAR(32) "
                "REFERENCES thesis_versions (id) ON DELETE SET NULL",
                "CREATE INDEX IF NOT EXISTS ix_evidence_thesis_version_id "
                "ON evidence (thesis_version_id)",
            ),
            (
                "saved_to_history",
                "ALTER TABLE evidence ADD COLUMN saved_to_history BOOLEAN " "NOT NULL DEFAULT 0",
                None,
            ),
            (
                "assumption_findings",
                "ALTER TABLE evidence ADD COLUMN assumption_findings JSON NOT NULL DEFAULT '[]'",
                None,
            ),
            (
                "score_delta",
                "ALTER TABLE evidence ADD COLUMN score_delta FLOAT NOT NULL DEFAULT 0",
                None,
            ),
            (
                "node_contributions",
                "ALTER TABLE evidence ADD COLUMN node_contributions JSON NOT NULL DEFAULT '[]'",
                None,
            ),
        ),
        "analysis_results": (
            (
                "thesis_version_id",
                "ALTER TABLE analysis_results ADD COLUMN thesis_version_id CHAR(32) "
                "REFERENCES thesis_versions (id) ON DELETE SET NULL",
                "CREATE INDEX IF NOT EXISTS ix_analysis_results_thesis_version_id "
                "ON analysis_results (thesis_version_id)",
            ),
        ),
        "theses": (
            (
                "template_id",
                "ALTER TABLE theses ADD COLUMN template_id VARCHAR(50) NOT NULL "
                "DEFAULT 'GENERAL_FUNDAMENTAL'",
                None,
            ),
            (
                "template_catalog_version",
                "ALTER TABLE theses ADD COLUMN template_catalog_version VARCHAR(20) "
                "NOT NULL DEFAULT '1.0.0'",
                None,
            ),
            (
                "template_snapshot",
                "ALTER TABLE theses ADD COLUMN template_snapshot JSON NOT NULL DEFAULT '{}'",
                None,
            ),
            (
                "assumption_bindings",
                "ALTER TABLE theses ADD COLUMN assumption_bindings JSON NOT NULL DEFAULT '[]'",
                None,
            ),
            (
                "logic_graph",
                "ALTER TABLE theses ADD COLUMN logic_graph JSON NOT NULL DEFAULT '{}'",
                None,
            ),
            (
                "score_breakdown",
                "ALTER TABLE theses ADD COLUMN score_breakdown JSON NOT NULL DEFAULT '{}'",
                None,
            ),
        ),
        "alerts": (
            (
                "is_scheduled",
                "ALTER TABLE alerts ADD COLUMN is_scheduled BOOLEAN NOT NULL DEFAULT 0",
                None,
            ),
        ),
        "users": (
            (
                "role",
                "ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'",
                None,
            ),
        ),
    }
    table_names = set(inspector.get_table_names())
    for table_name, columns in additive_columns.items():
        if table_name not in table_names:
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        for column_name, alter_sql, index_sql in columns:
            if column_name not in existing_columns:
                connection.exec_driver_sql(alter_sql)
            if index_sql is not None:
                connection.exec_driver_sql(index_sql)

    connection.exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS thesisguard_local_migrations "
        "(migration_id VARCHAR(100) PRIMARY KEY)"
    )
    centered_scores = connection.exec_driver_sql(
        "SELECT 1 FROM thesisguard_local_migrations "
        "WHERE migration_id = '0011_center_confidence_scores'"
    ).first()
    if centered_scores is not None:
        return

    migrated_inspector = inspect(connection)
    migrated_columns = {
        table_name: {
            column["name"] for column in migrated_inspector.get_columns(table_name)
        }
        for table_name in table_names
    }

    if "confidence_score" in migrated_columns.get("theses", set()):
        connection.exec_driver_sql(
            "UPDATE theses SET confidence_score = confidence_score - 50"
        )
    if "score_breakdown" in migrated_columns.get("theses", set()):
        connection.exec_driver_sql(
            """
            UPDATE theses
            SET score_breakdown = json_set(
                score_breakdown,
                '$.previous_score', json_extract(score_breakdown, '$.previous_score') - 50,
                '$.health_score', json_extract(score_breakdown, '$.health_score') - 50
            )
            WHERE json_valid(score_breakdown)
              AND json_type(score_breakdown, '$.previous_score') IN ('integer', 'real')
              AND json_type(score_breakdown, '$.health_score') IN ('integer', 'real')
            """
        )
    if "confidence_score" in migrated_columns.get("thesis_versions", set()):
        connection.exec_driver_sql(
            "UPDATE thesis_versions SET confidence_score = confidence_score - 50"
        )
    if "snapshot" in migrated_columns.get("thesis_versions", set()):
        connection.exec_driver_sql(
            """
            UPDATE thesis_versions
            SET snapshot = json_set(
                snapshot,
                '$.confidence_score', json_extract(snapshot, '$.confidence_score') - 50
            )
            WHERE json_valid(snapshot)
              AND json_type(snapshot, '$.confidence_score') IN ('integer', 'real')
            """
        )
        connection.exec_driver_sql(
            """
            UPDATE thesis_versions
            SET snapshot = json_set(
                snapshot,
                '$.score_breakdown.previous_score',
                    json_extract(snapshot, '$.score_breakdown.previous_score') - 50,
                '$.score_breakdown.health_score',
                    json_extract(snapshot, '$.score_breakdown.health_score') - 50
            )
            WHERE json_valid(snapshot)
              AND json_type(snapshot, '$.score_breakdown.previous_score')
                    IN ('integer', 'real')
              AND json_type(snapshot, '$.score_breakdown.health_score')
                    IN ('integer', 'real')
            """
        )
    if "raw_result" in migrated_columns.get("analysis_results", set()):
        connection.exec_driver_sql(
            """
            UPDATE analysis_results
            SET raw_result = json_set(
                raw_result,
                '$.updated_confidence', json_extract(raw_result, '$.updated_confidence') - 50
            )
            WHERE json_valid(raw_result)
              AND json_type(raw_result, '$.updated_confidence') IN ('integer', 'real')
            """
        )
        connection.exec_driver_sql(
            """
            UPDATE analysis_results
            SET raw_result = json_set(
                raw_result,
                '$.score_breakdown.previous_score',
                    json_extract(raw_result, '$.score_breakdown.previous_score') - 50,
                '$.score_breakdown.health_score',
                    json_extract(raw_result, '$.score_breakdown.health_score') - 50
            )
            WHERE json_valid(raw_result)
              AND json_type(raw_result, '$.score_breakdown.previous_score')
                    IN ('integer', 'real')
              AND json_type(raw_result, '$.score_breakdown.health_score')
                    IN ('integer', 'real')
            """
        )

    connection.exec_driver_sql(
        "INSERT INTO thesisguard_local_migrations (migration_id) "
        "VALUES ('0011_center_confidence_scores')"
    )


async def get_db() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
