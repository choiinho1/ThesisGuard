"""Alert Engine (ADR-0004): persists the alert C already decided on, and
sends CRITICAL/MAJOR immediately. MINOR alerts are stored unsent and picked
up by ``send_weekly_digest`` (wire that to a cron job / scheduled task —
no in-process scheduler is set up here, see backend/README.md)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from functools import lru_cache

from agents.alert_summary import (
    AlertContentSummarizer,
    AlertSummaryAgent,
    compact_alert_text,
)
from agents.models import AlertDecision
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from thesisguard_backend import models as orm
from thesisguard_backend.email_client import send_email

logger = logging.getLogger(__name__)


@lru_cache
def _default_summary_agent() -> AlertSummaryAgent:
    # Imported lazily to keep the provider-specific backend adapter out of the
    # reusable agents package and to avoid constructing a model when no alert fires.
    from thesisguard_backend.agent_adapters import create_chat_model

    return AlertSummaryAgent(create_chat_model())


async def _summarize_content(
    *,
    ticker: str,
    severity: str,
    content: str,
    summary_agent: AlertContentSummarizer | None,
) -> str:
    agent = summary_agent or _default_summary_agent()
    try:
        summary = await agent.summarize(ticker=ticker, severity=severity, content=content)
    except Exception:  # noqa: BLE001 - an LLM failure must not suppress a real alert
        logger.exception("alert summary agent failed: ticker=%s severity=%s", ticker, severity)
        summary = content
    return compact_alert_text(summary or content)


async def handle_alert_decision(
    db: AsyncSession,
    *,
    user: orm.User,
    portfolio: orm.Portfolio,
    thesis: orm.Thesis,
    ticker: str,
    decision: AlertDecision,
    is_scheduled: bool = False,
    summary_agent: AlertContentSummarizer | None = None,
) -> orm.Alert | None:
    if decision.severity == "NONE" or not decision.should_send:
        return None

    message = await _summarize_content(
        ticker=ticker,
        severity=str(decision.severity),
        content=decision.reason,
        summary_agent=summary_agent,
    )
    alert = orm.Alert(
        user_id=user.id,
        portfolio_id=portfolio.id,
        thesis_id=thesis.id,
        severity=decision.severity,
        delivery=orm.AlertDelivery(decision.delivery),
        title=f"[{decision.severity}] {ticker} 투자 논리 변화",
        message=message,
        is_sent=False,
        is_scheduled=is_scheduled,
    )
    db.add(alert)
    await db.flush()

    settings = await db.get(orm.AlertSettings, user.id)
    immediate_enabled = settings is None or settings.immediate_alerts_enabled
    # Email is scheduler-only: manual "재분석" still records an Alert (so the
    # UI can show it on the analysis result) but never emails the user, since
    # they're already watching the page live when they click it themselves.
    if decision.delivery == "IMMEDIATE" and immediate_enabled and is_scheduled:
        await send_email(user.email, alert.title, alert.message)
        alert.is_sent = True
        alert.sent_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(alert)
    return alert


async def send_weekly_digest(
    db: AsyncSession,
    user: orm.User,
    *,
    summary_agent: AlertContentSummarizer | None = None,
) -> int:
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

    digest_material = "\n\n".join(f"- {alert.title}: {alert.message}" for alert in pending)
    body = await _summarize_content(
        ticker="포트폴리오",
        severity="WEEKLY",
        content=digest_material,
        summary_agent=summary_agent,
    )
    await send_email(user.email, "ThesisGuard 주간 요약", body)
    now = datetime.now(UTC)
    for alert in pending:
        alert.is_sent = True
        alert.sent_at = now
    await db.commit()
    return len(pending)
