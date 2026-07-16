from pathlib import Path

from agents.evaluation.agent_benchmark import (
    classification_metrics,
    evaluate_alert_policy,
    excerpt_grounded,
    load_agent_metric_labels,
    validate_label_coverage,
)

ROOT = Path(__file__).parents[1]
LABELS = ROOT / "agents" / "evaluation" / "datasets" / "agent_metrics_v1.json"
RETRIEVAL_DATASET = (
    ROOT / "agents" / "evaluation" / "datasets" / "investment_rag_v1.json"
)


def test_agent_metric_labels_cover_every_retrieval_document() -> None:
    labels = load_agent_metric_labels(LABELS)

    validate_label_coverage(labels, RETRIEVAL_DATASET)

    assert sum(map(len, labels.classification_labels.values())) == 37
    assert len(labels.alert_cases) == 16


def test_classification_metrics_include_macro_f1_and_confusion_matrix() -> None:
    report = classification_metrics(
        ["SUPPORT", "CONTRADICT", "NEUTRAL", "NEUTRAL"],
        ["SUPPORT", "NEUTRAL", "NEUTRAL", "UNCERTAIN"],
    )

    assert report["samples"] == 4
    assert report["accuracy"] == 0.5
    assert report["confusion_matrix"]["CONTRADICT"]["NEUTRAL"] == 1
    assert report["confusion_matrix"]["NEUTRAL"]["UNCERTAIN"] == 1


def test_excerpt_grounded_checks_each_selected_passage() -> None:
    source = "Revenue increased 20 percent. Margin also expanded."

    assert excerpt_grounded("Revenue increased 20 percent.\nMargin also expanded.", source)
    assert not excerpt_grounded("Revenue increased 20 percent.\nInvented claim.", source)


def test_alert_policy_matches_human_labeled_policy_cases() -> None:
    labels = load_agent_metric_labels(LABELS)

    report = evaluate_alert_policy(labels.alert_cases)

    assert report["false_positive_rate"] == 0
    assert report["recall"] == 1
    assert report["policy_exact_match"] == 1
