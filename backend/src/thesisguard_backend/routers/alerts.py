"""GET /api/alerts, PATCH .../read, GET/PUT .../alert-settings"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from thesisguard_backend import models as orm
from thesisguard_backend.deps import CurrentUser, DbSession
from thesisguard_backend.schemas import AlertResponse, AlertSettingsRequest, AlertSettingsResponse

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts", response_model=list[AlertResponse])
async def list_alerts(db: DbSession, current_user: CurrentUser) -> list[orm.Alert]:
    result = await db.scalars(
        select(orm.Alert)
        .where(orm.Alert.user_id == current_user.id)
        .order_by(orm.Alert.created_at.desc())
    )
    return list(result)


@router.patch("/alerts/{alert_id}/read", response_model=AlertResponse)
async def mark_alert_read(alert_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> orm.Alert:
    alert = await db.get(orm.Alert, alert_id)
    if alert is None or alert.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "알림을 찾을 수 없습니다.")
    alert.is_sent = True
    await db.commit()
    await db.refresh(alert)
    return alert


@router.get("/users/me/alert-settings", response_model=AlertSettingsResponse)
async def get_alert_settings(db: DbSession, current_user: CurrentUser) -> orm.AlertSettings:
    settings = await db.get(orm.AlertSettings, current_user.id)
    if settings is None:
        settings = orm.AlertSettings(user_id=current_user.id)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


@router.put("/users/me/alert-settings", response_model=AlertSettingsResponse)
async def update_alert_settings(
    payload: AlertSettingsRequest, db: DbSession, current_user: CurrentUser
) -> orm.AlertSettings:
    settings = await db.get(orm.AlertSettings, current_user.id)
    if settings is None:
        settings = orm.AlertSettings(user_id=current_user.id)
        db.add(settings)
    settings.immediate_alerts_enabled = payload.immediate_alerts_enabled
    settings.weekly_digest_enabled = payload.weekly_digest_enabled
    await db.commit()
    await db.refresh(settings)
    return settings
