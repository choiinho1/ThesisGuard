"""Alert Engine (ADR-0004): persists the alert C already decided on, and
sends CRITICAL/MAJOR immediately. MINOR alerts are stored unsent and picked
up by ``send_weekly_digest`` (wire that to a cron job / scheduled task —
no in-process scheduler is set up here, see backend/README.md)."""

from __future__ import annotations

from datetime import UTC, datetime

from agents.models import AlertDecision
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from thesisguard_backend import models as orm
from thesisguard_backend.email_client import send_email


async def handle_alert_decision(
    db: AsyncSession,
    *,
    user: orm.User,
    portfolio: orm.Portfolio,
    thesis: orm.Thesis,
    ticker: str,
    decision: AlertDecision,
) -> orm.Alert | None:
    if decision.severity == "NONE" or not decision.should_send:
        return None

    alert = orm.Alert(
        user_id=user.id,
        portfolio_id=portfolio.id,
        thesis_id=thesis.id,
        severity=decision.severity,
        delivery=orm.AlertDelivery(decision.delivery),
        title=f"[{decision.severity}] {ticker} 투자 논리 변화",
        message=decision.reason,
        is_sent=False,
    )
    db.add(alert)
    await db.flush()

    settings = await db.get(orm.AlertSettings, user.id)
    immediate_enabled = settings is None or settings.immediate_alerts_enabled
    if decision.delivery == "IMMEDIATE" and immediate_enabled:
        await send_email(user.email, alert.title, alert.message)
        alert.is_sent = True
        alert.sent_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(alert)
    return alert


async def send_weekly_digest(db: AsyncSession, user: orm.User) -> int:
    """Email every unsent MINOR alert for a user in one digest. Returns count sent."""

    settings = await db.get(orm.AlertSettings, user.id)
    if settings is not None and not settings.weekly_digest_enabled:
        return 0

    pending = list(
        await db.scalars(
            select(orm.Alert).where(
                orm.Alert.user_id == user.id,
                orm.Alert.delivery == "WEEKLY",
                orm.Alert.is_sent.is_(False),
            )
        )
    )
    if not pending:
        return 0

    body = "\n\n".join(f"- {alert.title}: {alert.message}" for alert in pending)
    await send_email(user.email, "ThesisGuard 주간 요약", body)
    now = datetime.now(UTC)
    for alert in pending:
        alert.is_sent = True
        alert.sent_at = now
    await db.commit()
    return len(pending)
