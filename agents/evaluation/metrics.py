"""Pure metrics that can be wrapped by LangSmith evaluators."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from agents.models import EvidenceClassification, EvidenceItem


def accuracy(expected: Sequence[str], predicted: Sequence[str]) -> float:
    if len(expected) != len(predicted):
        raise ValueError("expected and predicted must have the same length")
    if not expected:
        return 0.0
    return sum(left == right for left, right in zip(expected, predicted, strict=True)) / len(
        expected
    )


def citation_groundedness(
    evidence: Iterable[EvidenceItem], source_text_by_document_id: Mapping[str, str]
) -> float:
    items = list(evidence)
    if not items:
        return 0.0
    grounded = sum(
        item.content_snippet in source_text_by_document_id.get(item.document_id, "")
        for item in items
    )
    return grounded / len(items)


def contradiction_recall(
    expected_contradiction_ids: set[str], predicted: Iterable[EvidenceItem]
) -> float:
    if not expected_contradiction_ids:
        return 1.0
    predicted_ids = {
        item.document_id
        for item in predicted
        if item.classification == EvidenceClassification.CONTRADICT
    }
    return len(expected_contradiction_ids & predicted_ids) / len(expected_contradiction_ids)


def portfolio_query_citation_precision(
    allowed_document_ids: set[str], predicted_document_ids: Iterable[str]
) -> float:
    """Measure whether a Portfolio Q&A answer cites only supplied evidence IDs."""

    predicted = set(predicted_document_ids)
    if not predicted:
        return 1.0
    return len(allowed_document_ids & predicted) / len(predicted)


def portfolio_query_citation_recall(
    expected_document_ids: set[str], predicted_document_ids: Iterable[str]
) -> float:
    """Measure whether a Portfolio Q&A answer cites the expected supporting evidence."""

    if not expected_document_ids:
        return 1.0
    return len(expected_document_ids & set(predicted_document_ids)) / len(expected_document_ids)


def portfolio_query_limitation_recall(
    required_keywords: set[str], predicted_limitations: Iterable[str]
) -> float:
    """Measure required limitation coverage using case-insensitive benchmark keywords."""

    if not required_keywords:
        return 1.0
    normalized = "\n".join(predicted_limitations).casefold()
    covered = sum(keyword.casefold() in normalized for keyword in required_keywords)
    return covered / len(required_keywords)
