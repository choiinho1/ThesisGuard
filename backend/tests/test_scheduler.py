from __future__ import annotations

from agents.models import EvidenceItem
from thesisguard_backend.scheduler import MIN_CONFIDENCE_DELTA_FOR_ALERT, score_delta_alert_decision

_SOURCED_EVIDENCE = [
    EvidenceItem(
        document_id="doc1",
        source_type="NEWS",
        source_url="https://example.com/news1",
        content_snippet="NVDA reported strong Q2 earnings driven by data center demand.",
        classification="SUPPORT",
        impact="HIGH",
        reason="positive earnings signal",
    )
]


def test_score_delta_below_threshold_does_not_alert() -> None:
    decision = score_delta_alert_decision(
        50, 50 + MIN_CONFIDENCE_DELTA_FOR_ALERT - 1, "NVDA", "reason", []
    )
    assert decision.severity == "NONE"
    assert decision.should_send is False
    assert decision.delivery == "NONE"


def test_score_delta_at_threshold_alerts_and_names_ticker() -> None:
    decision = score_delta_alert_decision(
        50, 50 + MIN_CONFIDENCE_DELTA_FOR_ALERT, "NVDA", "실적 호조", _SOURCED_EVIDENCE
    )
    assert decision.severity == "MAJOR"
    assert decision.should_send is True
    assert decision.delivery == "IMMEDIATE"
    assert "'NVDA'" in decision.reason
    assert "상승" in decision.reason


def test_score_delta_includes_change_reason_and_sourced_evidence() -> None:
    decision = score_delta_alert_decision(
        50, 60, "NVDA", "실적 발표가 예상치를 상회했습니다.", _SOURCED_EVIDENCE
    )
    assert "실적 발표가 예상치를 상회했습니다." in decision.reason
    assert "https://example.com/news1" in decision.reason
    # Each evidence bullet uses item.reason (C's natural-language explanation
    # of why the evidence matters), not the raw content_snippet — filing/
    # article text reads like unformatted boilerplate in an email.
    assert "positive earnings signal" in decision.reason
    assert "NVDA reported strong Q2 earnings" not in decision.reason


def test_score_delta_excludes_failed_classification_evidence() -> None:
    """UNCERTAIN evidence is C's fallback when its Gemini classification call
    fails (e.g. a 429 quota error), carrying an error string in `reason`. Those
    must never reach the email — only SUPPORT/CONTRADICT items are included."""

    failed = EvidenceItem(
        document_id="doc-x",
        source_type="SEC_FILING",
        source_url="https://sec.gov/x",
        content_snippet="raw filing text",
        classification="UNCERTAIN",
        impact="LOW",
        reason="분류 모델 오류(ChatGoogleGenerativeAIError)로 불확실 처리했습니다.",
    )
    decision = score_delta_alert_decision(
        50, 60, "NVDA", "실적 호조", [failed, *_SOURCED_EVIDENCE]
    )
    assert "ChatGoogleGenerativeAIError" not in decision.reason
    assert "positive earnings signal" in decision.reason


def test_score_delta_omits_evidence_section_when_all_failed() -> None:
    failed = EvidenceItem(
        document_id="doc-x",
        source_type="SEC_FILING",
        source_url="https://sec.gov/x",
        content_snippet="raw filing text",
        classification="UNCERTAIN",
        impact="LOW",
        reason="분류 모델 오류로 불확실 처리했습니다.",
    )
    decision = score_delta_alert_decision(50, 60, "NVDA", "실적 호조", [failed])
    assert decision.should_send is True
    assert "주요 근거" not in decision.reason


def test_score_delta_negative_direction_alerts() -> None:
    decision = score_delta_alert_decision(
        60, 60 - MIN_CONFIDENCE_DELTA_FOR_ALERT, "NVDA", "reason", []
    )
    assert decision.should_send is True
    assert "하락" in decision.reason


def test_score_delta_zero_change_does_not_alert() -> None:
    decision = score_delta_alert_decision(50, 50, "NVDA", "reason", [])
    assert decision.should_send is False
