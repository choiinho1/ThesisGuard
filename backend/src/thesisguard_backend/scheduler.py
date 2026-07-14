"""In-process background worker for per-holding daily auto-reanalysis
(05_선택종목_예약재분석 B-6/B-7).

Runs as a single asyncio task started from ``main.py``'s lifespan — one
sequential polling loop, so there is no multi-worker race to guard against
(if this ever moves to a separate process/replica, add ``SELECT ... FOR
UPDATE SKIP LOCKED`` when claiming a due schedule).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from thesisguard_backend import models as orm
from thesisguard_backend.config import get_settings
from thesisguard_backend.db import session_factory
from thesisguard_backend.routers.analysis import analyze_holding

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAYS_MINUTES = (5, 15)
STALE_THRESHOLD = timedelta(hours=12)


def compute_next_run_at(daily_time: time, timezone: str, *, after: datetime) -> datetime:
    """Next occurrence of ``daily_time`` (local to ``timezone``) strictly after ``after``."""

    tz = ZoneInfo(timezone)
    local_after = after.astimezone(tz)
    candidate = datetime.combine(local_after.date(), daily_time, tzinfo=tz)
    if candidate <= local_after:
        candidate += timedelta(days=1)
    return candidate.astimezone(UTC)


async def run_due_schedules() -> None:
    """Execute every enabled schedule whose next_run_at has passed."""

    now = datetime.now(UTC)
    async with session_factory() as db:
        due_ids = list(
            await db.scalars(
                select(orm.AnalysisSchedule.id).where(
                    orm.AnalysisSchedule.enabled.is_(True),
                    orm.AnalysisSchedule.next_run_at <= now,
                )
            )
        )

    for schedule_id in due_ids:
        try:
            await _execute_schedule(schedule_id)
        except Exception:  # noqa: BLE001 — one bad schedule must not stop the rest
            logger.exception("scheduled analysis run crashed: schedule_id=%s", schedule_id)


async def _execute_schedule(schedule_id: uuid.UUID) -> None:
    now = datetime.now(UTC)

    # Claim: verify the schedule is still due, record/refresh the run row for
    # this scheduled_for slot, and push next_run_at forward immediately so a
    # slow run can't be picked up twice by the next poll tick.
    async with session_factory() as db:
        schedule = await db.get(orm.AnalysisSchedule, schedule_id)
        if schedule is None or not schedule.enabled or schedule.next_run_at > now:
            return

        scheduled_for = schedule.next_run_at
        daily_time, timezone = schedule.daily_time, schedule.timezone
        holding = await db.get(orm.Holding, schedule.holding_id)
        portfolio = await db.get(orm.Portfolio, holding.portfolio_id)
        holding_id, user_id, ticker = holding.id, portfolio.user_id, holding.ticker

        run = await db.scalar(
            select(orm.ScheduledAnalysisRun).where(
                orm.ScheduledAnalysisRun.schedule_id == schedule.id,
                orm.ScheduledAnalysisRun.scheduled_for == scheduled_for,
            )
        )
        if run is None:
            run = orm.ScheduledAnalysisRun(
                schedule_id=schedule.id, holding_id=holding_id, scheduled_for=scheduled_for
            )
            db.add(run)

        if now - scheduled_for > STALE_THRESHOLD:
            run.status = orm.ScheduledRunStatus.SKIPPED
            run.started_at = now
            run.completed_at = now
            schedule.next_run_at = compute_next_run_at(daily_time, timezone, after=scheduled_for)
            await db.commit()
            return

        run.status = orm.ScheduledRunStatus.RUNNING
        run.started_at = now
        # Placeholder so a concurrent tick can't reclaim this schedule while
        # the analysis below is still in flight; overwritten with the real
        # value once the outcome (success/retry/failure) is known.
        schedule.next_run_at = now + timedelta(hours=1)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    try:
        async with session_factory() as db:
            holding = await db.get(orm.Holding, holding_id)
            user = await db.get(orm.User, user_id)
            result = await analyze_holding(holding, db, user)
    except Exception as exc:  # noqa: BLE001 — must persist the failure, not crash the loop
        await _record_failure(
            schedule_id=schedule_id,
            run_id=run_id,
            scheduled_for=scheduled_for,
            daily_time=daily_time,
            timezone=timezone,
            ticker=ticker,
            error=exc,
        )
        return

    async with session_factory() as db:
        run = await db.get(orm.ScheduledAnalysisRun, run_id)
        schedule = await db.get(orm.AnalysisSchedule, schedule_id)
        run.status = orm.ScheduledRunStatus.SUCCEEDED
        run.completed_at = datetime.now(UTC)
        run.thesis_version_id = result.version.id
        run.alert_id = result.alert.id if result.alert else None
        run.email_sent = bool(result.alert and result.alert.is_sent)
        schedule.last_run_at = datetime.now(UTC)
        schedule.next_run_at = compute_next_run_at(daily_time, timezone, after=scheduled_for)
        await db.commit()


async def _record_failure(
    *,
    schedule_id: uuid.UUID,
    run_id: uuid.UUID,
    scheduled_for: datetime,
    daily_time: time,
    timezone: str,
    ticker: str,
    error: Exception,
) -> None:
    async with session_factory() as db:
        run = await db.get(orm.ScheduledAnalysisRun, run_id)
        schedule = await db.get(orm.AnalysisSchedule, schedule_id)
        run.retry_count += 1
        run.error_message = str(error)[:2000]

        if run.retry_count > MAX_RETRIES:
            run.status = orm.ScheduledRunStatus.FAILED
            run.completed_at = datetime.now(UTC)
            schedule.next_run_at = compute_next_run_at(daily_time, timezone, after=scheduled_for)
        else:
            run.status = orm.ScheduledRunStatus.PENDING
            delay_minutes = RETRY_DELAYS_MINUTES[run.retry_count - 1]
            schedule.next_run_at = datetime.now(UTC) + timedelta(minutes=delay_minutes)

        await db.commit()
        retry_count = run.retry_count

    logger.warning(
        "scheduled analysis failed: ticker=%s retry_count=%s error=%s",
        ticker,
        retry_count,
        error,
    )


async def scheduler_loop() -> None:
    """Poll for due schedules every ``scheduler_poll_seconds``; runs until cancelled."""

    settings = get_settings()
    while True:
        try:
            await run_due_schedules()
        except Exception:  # noqa: BLE001 — a crashed tick must not kill the loop
            logger.exception("scheduler tick failed")
        await asyncio.sleep(max(5, settings.scheduler_poll_seconds))
