from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from agents.alert_summary import MAX_ALERT_SUMMARY_CHARS
from agents.models import AlertDecision
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from thesisguard_backend import alert_engine
from thesisguard_backend import models as orm
from thesisguard_backend.db import Base


class _SummaryAgent:
    def __init__(self, summary: str | None = None, error: Exception | None = None) -> None:
        self.summary = summary
        self.error = error
        self.calls: list[dict[str, str]] = []

    async def summarize(self, *, ticker: str, severity: str, content: str) -> str:
        self.calls.append({"ticker": ticker, "severity": severity, "content": content})
        if self.error is not None:
            raise self.error
        return self.summary or content


@pytest.fixture
async def alert_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user = orm.User(email="alerts@example.com", password_hash="hash")
        portfolio = orm.Portfolio(user=user, name="Test")
        holding = orm.Holding(portfolio=portfolio, ticker="MU", quantity=1, avg_buy_price=1)
        thesis = orm.Thesis(holding=holding, raw_input="메모리 수요", main_thesis="수요 증가")
        session.add(thesis)
        await session.commit()
        yield session, user, portfolio, thesis

    await engine.dispose()


@pytest.mark.asyncio
async def test_immediate_alert_and_email_share_agent_summary(alert_db, monkeypatch) -> None:
    db, user, portfolio, thesis = alert_db
    summary = "MU 신뢰도가 40점에서 47점으로 상승했습니다. HBM 장기계약이 핵심 근거입니다."
    agent = _SummaryAgent(summary=summary)
    send_email = AsyncMock()
    monkeypatch.setattr(alert_engine, "send_email", send_email)

    alert = await alert_engine.handle_alert_decision(
        db,
        user=user,
        portfolio=portfolio,
        thesis=thesis,
        ticker="MU",
        decision=AlertDecision(
            severity="MAJOR",
            should_send=True,
            delivery="IMMEDIATE",
            reason="원본 " * 300,
        ),
        is_scheduled=True,
        summary_agent=agent,
    )

    assert alert is not None
    assert alert.message == summary
    assert len(alert.message) <= MAX_ALERT_SUMMARY_CHARS
    send_email.assert_awaited_once_with(user.email, alert.title, summary)
    assert agent.calls[0]["content"].startswith("원본")


@pytest.mark.asyncio
async def test_agent_failure_falls_back_to_hard_limited_alert(alert_db) -> None:
    db, user, portfolio, thesis = alert_db
    agent = _SummaryAgent(error=RuntimeError("provider unavailable"))

    alert = await alert_engine.handle_alert_decision(
        db,
        user=user,
        portfolio=portfolio,
        thesis=thesis,
        ticker="MU",
        decision=AlertDecision(
            severity="MINOR",
            should_send=True,
            delivery="WEEKLY",
            reason="긴 알림 원문 " * 100,
        ),
        summary_agent=agent,
    )

    assert alert is not None
    assert len(alert.message) <= MAX_ALERT_SUMMARY_CHARS
    assert alert.message.endswith("…")


@pytest.mark.asyncio
async def test_weekly_email_body_is_summarized_under_200_characters(alert_db, monkeypatch) -> None:
    db, user, portfolio, _thesis = alert_db
    db.add_all(
        [
            orm.Alert(
                user=user,
                portfolio_id=portfolio.id,
                severity="MINOR",
                delivery="WEEKLY",
                title=f"주간 알림 {index}",
                message="개별 요약 내용 " * 20,
            )
            for index in range(3)
        ]
    )
    await db.commit()
    agent = _SummaryAgent(summary="이번 주에는 메모리 수요와 공급 계약 변화가 핵심입니다.")
    send_email = AsyncMock()
    monkeypatch.setattr(alert_engine, "send_email", send_email)

    sent = await alert_engine.send_weekly_digest(db, user, summary_agent=agent)

    assert sent == 3
    body = send_email.await_args.args[2]
    assert body == agent.summary
    assert len(body) <= MAX_ALERT_SUMMARY_CHARS
