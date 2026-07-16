"""Pure helpers for evidence-classification and alert-policy benchmarks."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agents.models import AlertDecision, AlertSeverity, EvidenceClassification, ThesisStatus
from agents.policy import decide_alert


class AlertGoldenCase(BaseModel):
    case_id: str
    previous_status: ThesisStatus
    current_status: ThesisStatus
    expected_should_send: bool
    expected_severity: AlertSeverity
    expected_delivery: str


class AgentMetricLabels(BaseModel):
    dataset_id: str
    labeling_method: str
    classification_labels: dict[str, dict[str, EvidenceClassification]]
    alert_cases: list[AlertGoldenCase]


def load_agent_metric_labels(path: Path) -> AgentMetricLabels:
    return AgentMetricLabels.model_validate_json(path.read_text(encoding="utf-8"))


def percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise ValueError("At least one value is required")
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction)


def excerpt_grounded(source_excerpt: str, source_text: str) -> bool:
    """Check every selected source passage against the original document text."""

    passages = [passage.strip() for passage in source_excerpt.splitlines() if passage.strip()]
    return bool(passages) and all(passage in source_text for passage in passages)


def classification_metrics(
    expected: Sequence[str],
    predicted: Sequence[str],
    *,
    labels: Sequence[str] = ("SUPPORT", "CONTRADICT", "NEUTRAL"),
) -> dict[str, Any]:
    if len(expected) != len(predicted):
        raise ValueError("expected and predicted must have the same length")
    if not expected:
        raise ValueError("At least one classification is required")

    confusion = {
        label: {predicted_label: 0 for predicted_label in (*labels, "UNCERTAIN", "ERROR")}
        for label in labels
    }
    for expected_label, predicted_label in zip(expected, predicted, strict=True):
        confusion[expected_label].setdefault(predicted_label, 0)
        confusion[expected_label][predicted_label] += 1

    per_class: dict[str, dict[str, float | int]] = {}
    for label in labels:
        true_positive = sum(
            left == label and right == label
            for left, right in zip(expected, predicted, strict=True)
        )
        false_positive = sum(
            left != label and right == label
            for left, right in zip(expected, predicted, strict=True)
        )
        false_negative = sum(
            left == label and right != label
            for left, right in zip(expected, predicted, strict=True)
        )
        precision_denominator = true_positive + false_positive
        recall_denominator = true_positive + false_negative
        precision = true_positive / precision_denominator if precision_denominator else 0.0
        recall = true_positive / recall_denominator if recall_denominator else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {
            "support": sum(left == label for left in expected),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    matches = sum(left == right for left, right in zip(expected, predicted, strict=True))
    accuracy = matches / len(expected)
    macro_f1 = sum(float(metrics["f1"]) for metrics in per_class.values()) / len(labels)
    return {
        "samples": len(expected),
        "accuracy": round(accuracy, 4),
        "macro_f1": round(macro_f1, 4),
        "per_class": per_class,
        "confusion_matrix": confusion,
    }


def evaluate_alert_policy(
    cases: Sequence[AlertGoldenCase],
    policy: Callable[[ThesisStatus, ThesisStatus], AlertDecision] = decide_alert,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    true_positive = false_positive = false_negative = true_negative = 0
    exact_policy_matches = 0

    for case in cases:
        decision = policy(case.previous_status, case.current_status)
        expected = case.expected_should_send
        predicted = decision.should_send
        if expected and predicted:
            true_positive += 1
        elif not expected and predicted:
            false_positive += 1
        elif expected and not predicted:
            false_negative += 1
        else:
            true_negative += 1

        exact_match = (
            predicted == expected
            and decision.severity == case.expected_severity
            and decision.delivery == case.expected_delivery
        )
        exact_policy_matches += int(exact_match)
        rows.append(
            {
                "case_id": case.case_id,
                "expected_should_send": expected,
                "predicted_should_send": predicted,
                "expected_severity": case.expected_severity.value,
                "predicted_severity": decision.severity.value,
                "expected_delivery": case.expected_delivery,
                "predicted_delivery": decision.delivery,
                "exact_match": exact_match,
            }
        )

    negative_count = false_positive + true_negative
    positive_count = true_positive + false_negative
    return {
        "samples": len(cases),
        "confusion": {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "true_negative": true_negative,
        },
        "false_positive_rate": (
            round(false_positive / negative_count, 4) if negative_count else None
        ),
        "recall": round(true_positive / positive_count, 4) if positive_count else None,
        "policy_exact_match": round(exact_policy_matches / len(cases), 4) if cases else 0.0,
        "cases": rows,
    }


def validate_label_coverage(
    labels: AgentMetricLabels,
    retrieval_dataset_path: Path,
) -> None:
    retrieval_cases = json.loads(retrieval_dataset_path.read_text(encoding="utf-8"))
    dataset_documents = {
        case["case_id"]: {document["document_id"] for document in case["documents"]}
        for case in retrieval_cases
    }
    labeled_documents = {
        case_id: set(document_labels)
        for case_id, document_labels in labels.classification_labels.items()
    }
    if dataset_documents != labeled_documents:
        raise ValueError("Classification labels must cover every retrieval document exactly once")
