"""In-process background worker for per-holding daily auto-reanalysis
(05_선택종목_예약재분석 B-6/B-7).

Runs as a single asyncio task started from ``main.py``'s lifespan — one
sequential polling loop, so there is no multi-worker race to guard against
(if this ever moves to a separate process/replica, add ``SELECT ... FOR
UPDATE SKIP LOCKED`` when claiming a due schedule).
"""

from __future__ import annotations

import asyncio
import functools
import logging
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from agents.models import AlertDecision, EvidenceClassification, EvidenceImpact, EvidenceItem
from sqlalchemy import select

from thesisguard_backend import models as orm
from thesisguard_backend import settings_service
from thesisguard_backend.db import session_factory
from thesisguard_backend.routers.analysis import run_analysis_and_save

logger = logging.getLogger(__name__)

# Fallback defaults, used only if the DB-backed AppSetting rows are somehow
# missing (settings_service.DEFAULT_SETTINGS is the source of truth an admin
# edits from the admin console — see settings_service.py).
MAX_RETRIES = 2
RETRY_DELAYS_MINUTES = (5, 15)
STALE_THRESHOLD = timedelta(hours=12)

# Scheduled runs alert on confidence-score movement alone (not C's LLM
# judgment, which is what manual /analyze still uses) — simple, predictable,
# and matches what users actually asked to be watched for.
MIN_CONFIDENCE_DELTA_FOR_ALERT = 5


def score_delta_alert_decision(
    previous_confidence: int,
    new_confidence: int,
    ticker: str,
    change_reason: str,
    evidence: list[EvidenceItem],
    *,
    min_confidence_delta: int | None = None,
) -> AlertDecision:
    threshold = (
        MIN_CONFIDENCE_DELTA_FOR_ALERT if min_confidence_delta is None else min_confidence_delta
    )
    delta = new_confidence - previous_confidence
    if abs(delta) < threshold:
        return AlertDecision(
            severity="NONE",
            should_send=False,
            delivery="NONE",
            reason=(
                f"'{ticker}' 신뢰도 변동폭이 {abs(delta)}점으로 임계값({threshold}점) 미만입니다."
            ),
        )
    direction = "상승" if delta > 0 else "하락"
    lines = [
        f"'{ticker}' 신뢰도가 {previous_confidence}점에서 {new_confidence}점으로 "
        f"{direction}했습니다.",
        "",
        "변화 근거:",
        change_reason,
    ]
    # Prefer SUPPORT/CONTRADICT evidence — those are the directional items that
    # actually explain a score move. Deterministic scoring can move confidence
    # ≥5 points from assumption/template recalculation alone, with every piece
    # of evidence classified NEUTRAL (nothing directly supports or contradicts
    # the thesis); in that case fall back to the highest-impact evidence so the
    # email isn't left with only the score line and no "주요 근거" at all. Either
    # way UNCERTAIN is excluded — that's what C falls back to when its
    # classification call fails (e.g. a 429 quota error), so a degraded run
    # never emails raw error-fallback text.
    directional_evidence = [
        item
        for item in evidence
        if item.source_url
        and item.classification
        in (EvidenceClassification.SUPPORT, EvidenceClassification.CONTRADICT)
    ]
    if not directional_evidence:
        directional_evidence = [
            item
            for item in evidence
            if item.source_url
            and item.classification != EvidenceClassification.UNCERTAIN
            and item.impact in (EvidenceImpact.HIGH, EvidenceImpact.MEDIUM)
        ]
    if directional_evidence:
        lines += ["", "주요 근거:"]
        # item.reason, not content_snippet: reason is C's own natural-language
        # explanation of why this evidence matters, not the raw filing/article
        # text (which reads like unformatted legal boilerplate in an email).
        lines += [f"- {item.reason} ({item.source_url})" for item in directional_evidence[:5]]
    lines += ["", "※ 본 메일은 정보 제공 목적이며 투자 권유가 아닙니다."]
    return AlertDecision(
        severity="MAJOR",
        should_send=True,
        delivery="IMMEDIATE",
        reason="\n".join(lines),
    )


def compute_next_run_at(
    daily_time: time,
    timezone: str,
    *,
    after: datetime,
    allow_current_minute: bool = False,
) -> datetime:
    """Return the next local occurrence of ``daily_time`` in UTC.

    A time input has minute precision. When a user saves during the selected
    minute, ``allow_current_minute`` makes the schedule immediately due instead
    of silently postponing it until the next day.
    """

    tz = ZoneInfo(timezone)
    local_after = after.astimezone(tz)
    candidate = datetime.combine(local_after.date(), daily_time, tzinfo=tz)
    if candidate <= local_after:
        if allow_current_minute and local_after < candidate + timedelta(minutes=1):
            return after.astimezone(UTC)
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

        stale_threshold_hours = await settings_service.aget_setting(
            db, "scheduler.stale_threshold_hours"
        )
        if now - scheduled_for > timedelta(hours=stale_threshold_hours):
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
            min_confidence_delta = await settings_service.aget_setting(
                db, "scheduler.min_confidence_delta_for_alert"
            )
            result = await run_analysis_and_save(
                holding,
                db,
                user,
                alert_decision_factory=functools.partial(
                    score_delta_alert_decision, min_confidence_delta=min_confidence_delta
                ),
                is_scheduled=True,
            )
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

        max_retries = await settings_service.aget_setting(db, "scheduler.max_retries")
        retry_delays_minutes = (
            await settings_service.aget_setting(db, "scheduler.retry_delay_minutes_first"),
            await settings_service.aget_setting(db, "scheduler.retry_delay_minutes_second"),
        )

        if run.retry_count > max_retries:
            run.status = orm.ScheduledRunStatus.FAILED
            run.completed_at = datetime.now(UTC)
            schedule.next_run_at = compute_next_run_at(daily_time, timezone, after=scheduled_for)
        else:
            run.status = orm.ScheduledRunStatus.PENDING
            delay_index = min(run.retry_count - 1, len(retry_delays_minutes) - 1)
            delay_minutes = retry_delays_minutes[delay_index]
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
    """Poll for due schedules every ``scheduler.poll_seconds``; runs until cancelled."""

    while True:
        try:
            await run_due_schedules()
        except Exception:  # noqa: BLE001 — a crashed tick must not kill the loop
            logger.exception("scheduler tick failed")
        async with session_factory() as db:
            poll_seconds = await settings_service.aget_setting(db, "scheduler.poll_seconds")
        await asyncio.sleep(max(5, poll_seconds))
