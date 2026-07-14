from __future__ import annotations

from sqlalchemy import create_engine, inspect

from thesisguard_backend.db import _upgrade_legacy_local_schema


def test_upgrade_legacy_local_schema_adds_version_columns_without_data_loss() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE thesis_versions (id CHAR(32) PRIMARY KEY)")
        connection.exec_driver_sql(
            "CREATE TABLE evidence (id CHAR(32) PRIMARY KEY, document_id TEXT NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE analysis_results (id CHAR(32) PRIMARY KEY, judge_summary TEXT)"
        )
        connection.exec_driver_sql(
            "INSERT INTO analysis_results (id, judge_summary) VALUES ('result-1', 'kept')"
        )

        _upgrade_legacy_local_schema(connection)
        # Startup is repeatable and must remain safe after the columns exist.
        _upgrade_legacy_local_schema(connection)

        inspector = inspect(connection)
        evidence_columns = {column["name"] for column in inspector.get_columns("evidence")}
        analysis_columns = {column["name"] for column in inspector.get_columns("analysis_results")}
        saved_summary = connection.exec_driver_sql(
            "SELECT judge_summary FROM analysis_results WHERE id = 'result-1'"
        ).scalar_one()

    assert "thesis_version_id" in evidence_columns
    assert "thesis_version_id" in analysis_columns
    assert saved_summary == "kept"
