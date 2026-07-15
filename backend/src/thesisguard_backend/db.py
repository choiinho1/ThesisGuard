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
                "score_breakdown",
                "ALTER TABLE theses ADD COLUMN score_breakdown JSON NOT NULL DEFAULT '{}'",
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


async def get_db() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
