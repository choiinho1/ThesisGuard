from datetime import UTC, datetime, time

import pytest

from thesisguard_backend.routers.analysis_schedules import calculate_next_run


def test_next_run_uses_requested_timezone() -> None:
    now = datetime(2026, 7, 14, 11, 0, tzinfo=UTC)  # 20:00 in Seoul
    assert calculate_next_run(time(21, 0), "Asia/Seoul", now) == datetime(
        2026, 7, 14, 12, 0, tzinfo=UTC
    )


def test_next_run_moves_to_tomorrow_after_daily_time() -> None:
    now = datetime(2026, 7, 14, 13, 0, tzinfo=UTC)  # 22:00 in Seoul
    assert calculate_next_run(time(21, 0), "Asia/Seoul", now) == datetime(
        2026, 7, 15, 12, 0, tzinfo=UTC
    )


def test_next_run_rejects_unknown_timezone() -> None:
    with pytest.raises(ValueError, match="Unknown IANA timezone"):
        calculate_next_run(time(21, 0), "Mars/Olympus")
