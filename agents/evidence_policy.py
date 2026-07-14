"""Shared gates for evidence that is strong enough to affect thesis judgment."""

from __future__ import annotations

from collections.abc import Iterable

from agents.models import (
    EvidenceClassification,
    EvidenceImpact,
    EvidenceItem,
)


def is_meaningful_directional_evidence(item: EvidenceItem) -> bool:
    return item.classification in {
        EvidenceClassification.SUPPORT,
        EvidenceClassification.CONTRADICT,
    } and item.impact in {EvidenceImpact.HIGH, EvidenceImpact.MEDIUM}


def meaningful_directional_evidence(evidence: Iterable[EvidenceItem]) -> list[EvidenceItem]:
    return [item for item in evidence if is_meaningful_directional_evidence(item)]
