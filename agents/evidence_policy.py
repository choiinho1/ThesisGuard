"""Deterministic policy for turning cited directions into scoring inputs."""

from __future__ import annotations

from collections.abc import Iterable

from agents.models import (
    AssumptionAssessment,
    AssumptionFinding,
    EvidenceClassification,
    EvidenceImpact,
    EvidenceItem,
    EvidenceSourceType,
)

_DIRECTIONAL_ASSESSMENTS = {
    AssumptionAssessment.SUPPORT,
    AssumptionAssessment.CONTRADICT,
}

# Source authority is the only input to the impact tier. The language model cannot
# increase or decrease this value. Non-directional or uncited findings are always LOW.
_DIRECTIONAL_IMPACT_BY_SOURCE = {
    EvidenceSourceType.SEC_FILING: EvidenceImpact.HIGH,
    EvidenceSourceType.EARNINGS: EvidenceImpact.HIGH,
    EvidenceSourceType.IR: EvidenceImpact.HIGH,
    EvidenceSourceType.NEWS: EvidenceImpact.MEDIUM,
    EvidenceSourceType.MACRO: EvidenceImpact.MEDIUM,
}


def deterministic_finding(
    *,
    assumption: str,
    assessment: AssumptionAssessment,
    source_passage_indices: list[int],
    source_type: EvidenceSourceType,
    invalid_reason: str | None = None,
) -> AssumptionFinding:
    """Materialize one model direction using code-owned relevance and impact rules."""

    cited_indices = list(dict.fromkeys(source_passage_indices))
    is_grounded = assessment in _DIRECTIONAL_ASSESSMENTS and bool(cited_indices)
    normalized_assessment = assessment if is_grounded else AssumptionAssessment.NOT_ADDRESSED
    if is_grounded:
        impact = _DIRECTIONAL_IMPACT_BY_SOURCE[source_type]
        relevance_score = 1.0
        reasoning = (
            f"원문 구간 {', '.join(map(str, cited_indices))}이 해당 가정을 직접 "
            f"{('지지' if assessment == AssumptionAssessment.SUPPORT else '반박')}합니다."
        )
    else:
        impact = EvidenceImpact.LOW
        relevance_score = 0.0
        reasoning = invalid_reason or "이 정보는 해당 가정을 직접 검증하지 않습니다."
        cited_indices = []

    return AssumptionFinding(
        assumption=assumption,
        assessment=normalized_assessment,
        impact=impact,
        relevance_score=relevance_score,
        reasoning=reasoning,
        source_passage_indices=cited_indices,
    )


def classification_from_findings(
    findings: list[AssumptionFinding],
) -> EvidenceClassification:
    """Derive the document-level label from grounded per-assumption directions."""

    directions = {
        finding.assessment
        for finding in findings
        if finding.assessment in _DIRECTIONAL_ASSESSMENTS
    }
    if directions == {AssumptionAssessment.SUPPORT}:
        return EvidenceClassification.SUPPORT
    if directions == {AssumptionAssessment.CONTRADICT}:
        return EvidenceClassification.CONTRADICT
    if directions:
        return EvidenceClassification.UNCERTAIN
    return EvidenceClassification.NEUTRAL


def impact_from_findings(findings: list[AssumptionFinding]) -> EvidenceImpact:
    """Return the code-owned document impact implied by grounded findings."""

    rank = {
        EvidenceImpact.LOW: 0,
        EvidenceImpact.MEDIUM: 1,
        EvidenceImpact.HIGH: 2,
    }
    return max((finding.impact for finding in findings), key=rank.get, default=EvidenceImpact.LOW)


def relevance_from_findings(findings: list[AssumptionFinding]) -> float:
    """Use binary relevance: at least one grounded direction is relevant."""

    return 1.0 if any(finding.relevance_score == 1.0 for finding in findings) else 0.0


def is_meaningful_directional_evidence(item: EvidenceItem) -> bool:
    return item.classification in {
        EvidenceClassification.SUPPORT,
        EvidenceClassification.CONTRADICT,
    } and item.impact in {EvidenceImpact.HIGH, EvidenceImpact.MEDIUM}


def meaningful_directional_evidence(evidence: Iterable[EvidenceItem]) -> list[EvidenceItem]:
    return [item for item in evidence if is_meaningful_directional_evidence(item)]
