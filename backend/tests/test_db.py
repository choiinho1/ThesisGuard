from __future__ import annotations

import json

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


def test_upgrade_legacy_local_schema_centers_existing_scores_once() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE theses ("
            "id TEXT PRIMARY KEY, confidence_score INTEGER NOT NULL, score_breakdown JSON NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE thesis_versions ("
            "id TEXT PRIMARY KEY, confidence_score INTEGER NOT NULL, snapshot JSON NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE analysis_results (id TEXT PRIMARY KEY, raw_result JSON NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO theses VALUES (?, ?, ?)",
            (
                "thesis-1",
                82,
                json.dumps({"previous_score": 50, "health_score": 82}),
            ),
        )
        connection.exec_driver_sql(
            "INSERT INTO thesis_versions VALUES (?, ?, ?)",
            (
                "version-1",
                54,
                json.dumps(
                    {
                        "confidence_score": 50,
                        "score_breakdown": {
                            "previous_score": 50,
                            "health_score": 54,
                        },
                    }
                ),
            ),
        )
        connection.exec_driver_sql(
            "INSERT INTO analysis_results VALUES (?, ?)",
            (
                "analysis-1",
                json.dumps(
                    {
                        "updated_confidence": 54,
                        "score_breakdown": {
                            "previous_score": 50,
                            "health_score": 54,
                        },
                    }
                ),
            ),
        )

        _upgrade_legacy_local_schema(connection)
        _upgrade_legacy_local_schema(connection)

        thesis_score, thesis_breakdown = connection.exec_driver_sql(
            "SELECT confidence_score, score_breakdown FROM theses WHERE id = 'thesis-1'"
        ).one()
        version_score, version_snapshot = connection.exec_driver_sql(
            "SELECT confidence_score, snapshot FROM thesis_versions WHERE id = 'version-1'"
        ).one()
        raw_result = connection.exec_driver_sql(
            "SELECT raw_result FROM analysis_results WHERE id = 'analysis-1'"
        ).scalar_one()

    assert thesis_score == 32
    assert json.loads(thesis_breakdown) == {"previous_score": 0, "health_score": 32}
    assert version_score == 4
    assert json.loads(version_snapshot) == {
        "confidence_score": 0,
        "score_breakdown": {"previous_score": 0, "health_score": 4},
    }
    assert json.loads(raw_result) == {
        "updated_confidence": 4,
        "score_breakdown": {"previous_score": 0, "health_score": 4},
    }
