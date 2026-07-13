from __future__ import annotations

import pytest
from pydantic import ValidationError

from thesisguard_agent.models import EvidenceItem, ThesisStatus
from thesisguard_agent.policy import decide_alert


def test_evidence_requires_a_valid_source_url() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(
            document_id="doc-1",
            source_type="NEWS",
            source_url="not-a-url",
            content_snippet="citation",
            classification="SUPPORT",
            impact=0.5,
            reason="reason",
        )


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

