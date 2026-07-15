from __future__ import annotations

from sqlalchemy import create_engine, inspect

from thesisguard_backend.db import _upgrade_legacy_local_schema


def test_upgrade_legacy_local_schema_adds_version_columns_without_data_loss() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE theses (id CHAR(32) PRIMARY KEY, main_thesis TEXT NOT NULL)"
        )
        connection.exec_driver_sql("CREATE TABLE thesis_versions (id CHAR(32) PRIMARY KEY)")
        connection.exec_driver_sql(
            "CREATE TABLE evidence (id CHAR(32) PRIMARY KEY, document_id TEXT NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO evidence (id, document_id) VALUES ('evidence-1', 'doc-1')"
        )
        connection.exec_driver_sql(
            "CREATE TABLE alerts (id CHAR(32) PRIMARY KEY, title TEXT NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO alerts (id, title) VALUES ('alert-1', 'kept alert')"
        )
        connection.exec_driver_sql(
            "CREATE TABLE analysis_results (id CHAR(32) PRIMARY KEY, judge_summary TEXT)"
        )
        connection.exec_driver_sql(
            "INSERT INTO analysis_results (id, judge_summary) VALUES ('result-1', 'kept')"
        )
        connection.exec_driver_sql(
            "INSERT INTO theses (id, main_thesis) VALUES ('thesis-1', 'kept thesis')"
        )

        _upgrade_legacy_local_schema(connection)
        # Startup is repeatable and must remain safe after the columns exist.
        _upgrade_legacy_local_schema(connection)

        inspector = inspect(connection)
        evidence_columns = {column["name"] for column in inspector.get_columns("evidence")}
        alert_columns = {column["name"] for column in inspector.get_columns("alerts")}
        analysis_columns = {column["name"] for column in inspector.get_columns("analysis_results")}
        thesis_columns = {column["name"] for column in inspector.get_columns("theses")}
        saved_summary = connection.exec_driver_sql(
            "SELECT judge_summary FROM analysis_results WHERE id = 'result-1'"
        ).scalar_one()
        saved_thesis = connection.exec_driver_sql(
            "SELECT main_thesis, template_id, template_catalog_version, logic_graph "
            "FROM theses WHERE id = 'thesis-1'"
        ).one()
        saved_evidence = connection.exec_driver_sql(
            "SELECT document_id, saved_to_history, assumption_findings, score_delta, "
            "node_contributions FROM evidence WHERE id = 'evidence-1'"
        ).one()
        saved_alert = connection.exec_driver_sql(
            "SELECT title, is_scheduled FROM alerts WHERE id = 'alert-1'"
        ).one()

    assert "thesis_version_id" in evidence_columns
    assert "saved_to_history" in evidence_columns
    assert {"assumption_findings", "score_delta", "node_contributions"} <= evidence_columns
    assert "is_scheduled" in alert_columns
    assert "thesis_version_id" in analysis_columns
    assert {
        "template_id",
        "template_catalog_version",
        "template_snapshot",
        "assumption_bindings",
        "logic_graph",
        "score_breakdown",
    } <= thesis_columns
    assert saved_summary == "kept"
    assert saved_thesis == ("kept thesis", "GENERAL_FUNDAMENTAL", "1.0.0", "{}")
    assert saved_evidence == ("doc-1", 0, "[]", 0.0, "[]")
    assert saved_alert == ("kept alert", 0)
