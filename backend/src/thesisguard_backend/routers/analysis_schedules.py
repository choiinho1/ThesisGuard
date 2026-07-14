"""Per-holding daily analysis schedule API."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from thesisguard_backend import models as orm
from thesisguard_backend.deps import CurrentUser, DbSession
from thesisguard_backend.routers.holdings import OwnedHolding
from thesisguard_backend.schemas import AnalysisScheduleRequest, AnalysisScheduleResponse

router = APIRouter(tags=["analysis-schedules"])


def calculate_next_run(daily_time: time, timezone: str, now: datetime | None = None) -> datetime:
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown IANA timezone: {timezone}") from exc
    current = (now or datetime.now(UTC)).astimezone(zone)
    candidate = current.replace(
        hour=daily_time.hour, minute=daily_time.minute, second=0, microsecond=0
    )
    if candidate <= current:
        candidate += timedelta(days=1)
    return candidate.astimezone(UTC)


async def _response(db: DbSession, schedule: orm.AnalysisSchedule) -> AnalysisScheduleResponse:
    holding = await db.get(orm.Holding, schedule.holding_id)
    last_status = await db.scalar(
        select(orm.ScheduledAnalysisRun.status)
        .where(orm.ScheduledAnalysisRun.schedule_id == schedule.id)
        .order_by(orm.ScheduledAnalysisRun.created_at.desc())
        .limit(1)
    )
    return AnalysisScheduleResponse(
        id=schedule.id,
        holding_id=schedule.holding_id,
        ticker=holding.ticker,
        enabled=schedule.enabled,
        daily_time=schedule.daily_time,
        timezone=schedule.timezone,
        recipient_email=schedule.recipient_email,
        last_run_at=schedule.last_run_at,
        last_run_status=last_status.value if last_status else None,
        next_run_at=schedule.next_run_at,
    )


@router.get("/api/analysis-schedules", response_model=list[AnalysisScheduleResponse])
async def list_schedules(db: DbSession, current_user: CurrentUser):
    schedules = list(
        await db.scalars(
            select(orm.AnalysisSchedule)
            .join(orm.Holding)
            .join(orm.Portfolio)
            .where(orm.Portfolio.user_id == current_user.id)
            .order_by(orm.AnalysisSchedule.next_run_at)
        )
    )
    return [await _response(db, item) for item in schedules]


@router.get(
    "/api/holdings/{holding_id}/analysis-schedule",
    response_model=AnalysisScheduleResponse,
)
async def get_schedule(holding: OwnedHolding, db: DbSession):
    schedule = await db.scalar(
        select(orm.AnalysisSchedule).where(orm.AnalysisSchedule.holding_id == holding.id)
    )
    if schedule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis schedule not found")
    return await _response(db, schedule)


@router.put(
    "/api/holdings/{holding_id}/analysis-schedule",
    response_model=AnalysisScheduleResponse,
)
async def put_schedule(
    payload: AnalysisScheduleRequest,
    holding: OwnedHolding,
    db: DbSession,
    current_user: CurrentUser,
):
    thesis = await db.scalar(select(orm.Thesis.id).where(orm.Thesis.holding_id == holding.id))
    if payload.enabled and thesis is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Register an investment thesis first")
    try:
        next_run_at = calculate_next_run(payload.daily_time, payload.timezone)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    schedule = await db.scalar(
        select(orm.AnalysisSchedule).where(orm.AnalysisSchedule.holding_id == holding.id)
    )
    if schedule is None:
        schedule = orm.AnalysisSchedule(holding_id=holding.id, recipient_email=current_user.email)
        db.add(schedule)
    schedule.enabled = payload.enabled
    schedule.daily_time = payload.daily_time
    schedule.timezone = payload.timezone
    schedule.recipient_email = current_user.email
    schedule.next_run_at = next_run_at
    await db.commit()
    await db.refresh(schedule)
    return await _response(db, schedule)


@router.delete("/api/holdings/{holding_id}/analysis-schedule", status_code=204)
async def delete_schedule(holding: OwnedHolding, db: DbSession) -> None:
    schedule = await db.scalar(
        select(orm.AnalysisSchedule).where(orm.AnalysisSchedule.holding_id == holding.id)
    )
    if schedule is not None:
        await db.delete(schedule)
        await db.commit()
