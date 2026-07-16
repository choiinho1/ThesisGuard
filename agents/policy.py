"""Deterministic alert policy from ADR-0004."""

from __future__ import annotations

from agents.models import (
    AlertDecision,
    AlertSeverity,
    ThesisStatus,
)

_STATUS_SCORE = {
    ThesisStatus.BROKEN: 0,
    ThesisStatus.STRONGLY_WEAKENED: 1,
    ThesisStatus.WEAKENED: 2,
    ThesisStatus.UNCHANGED: 3,
    ThesisStatus.STRENGTHENED: 4,
    ThesisStatus.STRONGLY_STRENGTHENED: 5,
}


def decide_alert(
    previous: ThesisStatus,
    current: ThesisStatus,
    *,
    major_movement_threshold: int | None = None,
) -> AlertDecision:
    """Map a six-step thesis change to the four alert severities."""

    movement = _STATUS_SCORE[current] - _STATUS_SCORE[previous]
    major_threshold = -2 if major_movement_threshold is None else major_movement_threshold

    if current == ThesisStatus.BROKEN:
        return AlertDecision(
            severity=AlertSeverity.CRITICAL,
            should_send=True,
            delivery="IMMEDIATE",
            reason="투자 논리가 BROKEN 상태로 판정되었습니다.",
        )
    if current == ThesisStatus.STRONGLY_WEAKENED or movement <= major_threshold:
        return AlertDecision(
            severity=AlertSeverity.MAJOR,
            should_send=True,
            delivery="IMMEDIATE",
            reason="투자 논리가 크게 약화되어 즉시 확인이 필요합니다.",
        )
    if current == ThesisStatus.WEAKENED or movement < 0:
        return AlertDecision(
            severity=AlertSeverity.MINOR,
            should_send=True,
            delivery="WEEKLY",
            reason="투자 논리가 소폭 약화되어 주간 요약에 포함합니다.",
        )
    return AlertDecision(
        severity=AlertSeverity.NONE,
        should_send=False,
        delivery="NONE",
        reason="즉시 알림이 필요한 약화 신호가 없습니다.",
    )
