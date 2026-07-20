from __future__ import annotations

import pytest
from pydantic import ValidationError

from agents.evidence_policy import deterministic_finding
from agents.models import (
    AssumptionAssessment,
    EvidenceImpact,
    EvidenceItem,
    EvidenceModelOutput,
    EvidenceSourceType,
    ThesisStatus,
)
from agents.policy import decide_alert


def test_evidence_requires_a_valid_source_url() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(
            document_id="doc-1",
            source_type="NEWS",
            source_url="not-a-url",
            content_snippet="citation",
            classification="SUPPORT",
            impact="HIGH",
            reason="reason",
        )


def test_model_evidence_output_rejects_numeric_scoring_fields() -> None:
    with pytest.raises(ValidationError):
        EvidenceModelOutput.model_validate(
            {
                "impact": "HIGH",
                "relevance_score": 0.99,
                "assumption_findings": [],
                "content_snippet": "모델은 점수 입력을 정할 수 없습니다.",
            }
        )


@pytest.mark.parametrize(
    ("source_type", "expected_impact"),
    [
        (EvidenceSourceType.SEC_FILING, EvidenceImpact.HIGH),
        (EvidenceSourceType.EARNINGS, EvidenceImpact.HIGH),
        (EvidenceSourceType.IR, EvidenceImpact.HIGH),
        (EvidenceSourceType.NEWS, EvidenceImpact.MEDIUM),
        (EvidenceSourceType.MACRO, EvidenceImpact.MEDIUM),
    ],
)
def test_grounded_direction_uses_code_owned_relevance_and_impact(
    source_type: EvidenceSourceType,
    expected_impact: EvidenceImpact,
) -> None:
    finding = deterministic_finding(
        assumption="매출 성장",
        assessment=AssumptionAssessment.SUPPORT,
        source_passage_indices=[0],
        source_type=source_type,
    )

    assert finding.relevance_score == 1.0
    assert finding.impact == expected_impact


def test_uncited_direction_is_excluded_by_code_owned_policy() -> None:
    finding = deterministic_finding(
        assumption="매출 성장",
        assessment=AssumptionAssessment.CONTRADICT,
        source_passage_indices=[],
        source_type=EvidenceSourceType.SEC_FILING,
    )

    assert finding.assessment == AssumptionAssessment.NOT_ADDRESSED
    assert finding.relevance_score == 0
    assert finding.impact == EvidenceImpact.LOW


@pytest.mark.parametrize(
    ("current", "severity", "delivery"),
    [
        (ThesisStatus.BROKEN, "CRITICAL", "IMMEDIATE"),
        (ThesisStatus.STRONGLY_WEAKENED, "MAJOR", "IMMEDIATE"),
        (ThesisStatus.WEAKENED, "MINOR", "WEEKLY"),
        (ThesisStatus.UNCHANGED, "NONE", "NONE"),
        (ThesisStatus.STRENGTHENED, "NONE", "NONE"),
    ],
)
def test_alert_policy(current: ThesisStatus, severity: str, delivery: str) -> None:
    decision = decide_alert(ThesisStatus.UNCHANGED, current)

    assert decision.severity == severity
    assert decision.delivery == delivery
