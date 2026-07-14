"""Per-holding daily auto-reanalysis schedule CRUD (05_선택종목_예약재분석 B-4)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from thesisguard_backend import models as orm
from thesisguard_backend.deps import CurrentUser, DbSession
from thesisguard_backend.routers.holdings import OwnedHolding
from thesisguard_backend.scheduler import compute_next_run_at
from thesisguard_backend.schemas import AnalysisScheduleRequest, AnalysisScheduleResponse

router = APIRouter(tags=["analysis-schedules"])


async def _response(db: DbSession, schedule: orm.AnalysisSchedule) -> AnalysisScheduleResponse:
    holding = await db.get(orm.Holding, schedule.holding_id)
    last_status = await db.scalar(
        select(orm.ScheduledAnalysisRun.status)
        .where(orm.ScheduledAnalysisRun.schedule_id == schedule.id)
        .order_by(orm.ScheduledAnalysisRun.scheduled_for.desc())
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
        last_run_status=last_status if last_status else None,
        next_run_at=schedule.next_run_at,
    )


@router.get("/api/analysis-schedules", response_model=list[AnalysisScheduleResponse])
async def list_schedules(db: DbSession, current_user: CurrentUser) -> list[AnalysisScheduleResponse]:
    schedules = list(
        await db.scalars(
            select(orm.AnalysisSchedule)
            .join(orm.Holding, orm.Holding.id == orm.AnalysisSchedule.holding_id)
            .join(orm.Portfolio, orm.Portfolio.id == orm.Holding.portfolio_id)
            .where(orm.Portfolio.user_id == current_user.id)
            .order_by(orm.AnalysisSchedule.next_run_at)
        )
    )
    return [await _response(db, item) for item in schedules]


@router.get(
    "/api/holdings/{holding_id}/analysis-schedule", response_model=AnalysisScheduleResponse
)
async def get_schedule(holding: OwnedHolding, db: DbSession) -> AnalysisScheduleResponse:
    schedule = await db.scalar(
        select(orm.AnalysisSchedule).where(orm.AnalysisSchedule.holding_id == holding.id)
    )
    if schedule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "등록된 예약이 없습니다.")
    return await _response(db, schedule)


@router.put(
    "/api/holdings/{holding_id}/analysis-schedule", response_model=AnalysisScheduleResponse
)
async def put_schedule(
    payload: AnalysisScheduleRequest,
    holding: OwnedHolding,
    db: DbSession,
    current_user: CurrentUser,
) -> AnalysisScheduleResponse:
    thesis_id = await db.scalar(select(orm.Thesis.id).where(orm.Thesis.holding_id == holding.id))
    if payload.enabled and thesis_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "투자 논리가 등록된 종목만 자동 재분석을 예약할 수 있습니다."
        )

    schedule = await db.scalar(
        select(orm.AnalysisSchedule).where(orm.AnalysisSchedule.holding_id == holding.id)
    )
    next_run_at = compute_next_run_at(payload.daily_time, payload.timezone, after=datetime.now(UTC))
    if schedule is None:
        schedule = orm.AnalysisSchedule(
            holding_id=holding.id,
            enabled=payload.enabled,
            daily_time=payload.daily_time,
            timezone=payload.timezone,
            recipient_email=current_user.email,
            next_run_at=next_run_at,
        )
        db.add(schedule)
    else:
        schedule.enabled = payload.enabled
        schedule.daily_time = payload.daily_time
        schedule.timezone = payload.timezone
        schedule.recipient_email = current_user.email
        schedule.next_run_at = next_run_at

    await db.commit()
    await db.refresh(schedule)
    return await _response(db, schedule)


@router.delete(
    "/api/holdings/{holding_id}/analysis-schedule", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_schedule(holding: OwnedHolding, db: DbSession) -> None:
    schedule = await db.scalar(
        select(orm.AnalysisSchedule).where(orm.AnalysisSchedule.holding_id == holding.id)
    )
    if schedule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "등록된 예약이 없습니다.")
    await db.delete(schedule)
    await db.commit()
