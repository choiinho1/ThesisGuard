"""Deterministic validation helpers for model-generated portfolio findings."""

from __future__ import annotations

_ABSENCE_MARKERS = (
    "없음",
    "none",
    "no theme",
    "no concentration",
    "no common",
    "no shared",
    "not detected",
    "not found",
    "미탐지",
)


def is_absence_label(value: str) -> bool:
    normalized = " ".join(value.casefold().split())
    return not normalized or any(marker in normalized for marker in _ABSENCE_MARKERS)
