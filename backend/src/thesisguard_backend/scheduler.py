"""Small database-backed scheduler for daily holding analysis."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from thesisguard_backend import models as orm
from thesisguard_backend.config import get_settings
from thesisguard_backend.db import session_factory
from thesisguard_backend.routers.analysis import analyze_holding
from thesisguard_backend.routers.analysis_schedules import calculate_next_run

logger = logging.getLogger(__name__)


async def run_due_schedules(now: datetime | None = None) -> int:
    current = now or datetime.now(UTC)
    async with session_factory() as db:
        due = list(
            await db.scalars(
                select(orm.AnalysisSchedule)
                .where(
                    orm.AnalysisSchedule.enabled.is_(True),
                    orm.AnalysisSchedule.next_run_at <= current,
                )
                .options(selectinload(orm.AnalysisSchedule.holding))
            )
        )
        completed = 0
        for schedule in due:
            scheduled_for = schedule.next_run_at
            run = orm.ScheduledAnalysisRun(
                schedule_id=schedule.id,
                holding_id=schedule.holding_id,
                scheduled_for=scheduled_for,
                status=orm.ScheduledRunStatus.RUNNING,
                started_at=current,
            )
            db.add(run)
            try:
                await db.flush()
            except IntegrityError:
                await db.rollback()
                continue

            if current - scheduled_for > timedelta(hours=12):
                run.status = orm.ScheduledRunStatus.SKIPPED
                run.completed_at = current
            else:
                portfolio = await db.get(orm.Portfolio, schedule.holding.portfolio_id)
                user = await db.get(orm.User, portfolio.user_id)
                try:
                    result = await analyze_holding(schedule.holding, db, user)
                    run.status = orm.ScheduledRunStatus.SUCCEEDED
                    run.thesis_version_id = result.version.id
                    run.alert_id = result.alert.id if result.alert else None
                    run.email_sent = bool(result.alert and result.alert.is_sent)
                    completed += 1
                except Exception as exc:  # worker must continue with other tickers
                    logger.exception("Scheduled analysis failed schedule_id=%s", schedule.id)
                    run.status = orm.ScheduledRunStatus.FAILED
                    run.error_message = str(exc)[:2000]
            run.completed_at = datetime.now(UTC)
            schedule.last_run_at = run.completed_at
            schedule.next_run_at = calculate_next_run(
                schedule.daily_time, schedule.timezone, schedule.next_run_at + timedelta(seconds=1)
            )
            await db.commit()
        return completed


async def scheduler_loop() -> None:
    settings = get_settings()
    while True:
        try:
            await run_due_schedules()
        except Exception:
            logger.exception("Analysis scheduler poll failed")
        await asyncio.sleep(max(5, settings.scheduler_poll_seconds))
