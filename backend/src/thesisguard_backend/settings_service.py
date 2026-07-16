"""Admin-tunable runtime parameters, backed by the ``app_settings`` table.

Lets an admin change scoring/alert/scheduler/LLM/RAG parameters from the
admin UI and have the next analysis run (or scheduler tick) pick them up
without a redeploy. Values are cached in-process for SETTING_CACHE_SECONDS
to avoid a DB round trip on every read; writes invalidate the cache
immediately.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from thesisguard_backend import models as orm

SETTING_CACHE_SECONDS = 30


@dataclass(frozen=True)
class SettingDefault:
    category: str
    value: Any
    description: str


# Hardcoded values these mirror (kept in sync manually, see docstrings at the
# call sites in agents/scoring.py, agents/policy.py, backend/scheduler.py,
# backend/agent_adapters.py, backend/routers/analysis.py, agents/rag.py).
DEFAULT_SETTINGS: dict[str, SettingDefault] = {
    "scoring.impact_weight_low": SettingDefault(
        "scoring", 0.09, "LOW-impact evidence의 신호 강도 가중치 (agents/scoring.py)"
    ),
    "scoring.impact_weight_medium": SettingDefault(
        "scoring", 0.27, "MEDIUM-impact evidence의 신호 강도 가중치"
    ),
    "scoring.impact_weight_high": SettingDefault(
        "scoring", 0.54, "HIGH-impact evidence의 신호 강도 가중치"
    ),
    "scoring.invalidation_streak_required": SettingDefault(
        "scoring", 2, "논리 무효화(BROKEN) 판정에 필요한 연속 반박 근거 횟수"
    ),
    "policy.major_movement_threshold": SettingDefault(
        "policy", -2, "MAJOR 알림으로 분류되는 상태 하락 폭 (agents/policy.py)"
    ),
    "scheduler.max_retries": SettingDefault("scheduler", 2, "예약 재분석 실패 시 최대 재시도 횟수"),
    "scheduler.retry_delay_minutes_first": SettingDefault(
        "scheduler", 5, "첫 번째 재시도까지 대기 시간(분)"
    ),
    "scheduler.retry_delay_minutes_second": SettingDefault(
        "scheduler", 15, "두 번째 재시도까지 대기 시간(분)"
    ),
    "scheduler.stale_threshold_hours": SettingDefault(
        "scheduler", 12, "이 시간(시간)을 넘긴 예약은 건너뛰고 SKIPPED 처리"
    ),
    "scheduler.poll_seconds": SettingDefault(
        "scheduler", 60, "스케줄러가 예약 목록을 확인하는 주기(초)"
    ),
    "scheduler.min_confidence_delta_for_alert": SettingDefault(
        "scheduler", 5, "예약 재분석에서 알림을 보낼 최소 신뢰도 변동폭"
    ),
    "llm.temperature": SettingDefault("llm", 0, "분석에 사용하는 LLM temperature"),
    "llm.timeout_seconds": SettingDefault("llm", 30, "LLM 호출 타임아웃(초)"),
    "llm.max_retries": SettingDefault("llm", 1, "LLM 호출 실패 시 재시도 횟수"),
    "rag.dense_candidate_ratio": SettingDefault(
        "rag", 0.2, "하이브리드 RAG에서 dense 검색이 차지하는 후보 비율"
    ),
    "qa.evidence_limit": SettingDefault(
        "qa", 50, "포트폴리오 질의에 사용하는 최근 Evidence 최대 개수"
    ),
}

_cache: dict[str, tuple[Any, float]] = {}


def _cache_get(key: str) -> tuple[bool, Any]:
    entry = _cache.get(key)
    if entry is None:
        return False, None
    value, expires_at = entry
    if time.monotonic() >= expires_at:
        return False, None
    return True, value


def _cache_put(key: str, value: Any) -> None:
    _cache[key] = (value, time.monotonic() + SETTING_CACHE_SECONDS)


def invalidate_cache(key: str | None = None) -> None:
    if key is None:
        _cache.clear()
    else:
        _cache.pop(key, None)


async def aget_setting(db: AsyncSession, key: str) -> Any:
    hit, value = _cache_get(key)
    if hit:
        return value
    row = await db.scalar(select(orm.AppSetting).where(orm.AppSetting.key == key))
    if row is not None:
        resolved = row.value.get("v") if isinstance(row.value, dict) else row.value
    else:
        default = DEFAULT_SETTINGS.get(key)
        if default is None:
            raise KeyError(f"Unknown setting key: {key!r}")
        resolved = default.value
    _cache_put(key, resolved)
    return resolved


async def aget_settings_snapshot(db: AsyncSession) -> dict[str, Any]:
    """All known settings' current effective values, for EvalRun.settings_snapshot."""

    return {key: await aget_setting(db, key) for key in DEFAULT_SETTINGS}


async def alist_settings(db: AsyncSession) -> list[orm.AppSetting]:
    """All settings rows, seeding any missing defaults first so the admin UI sees everything."""

    await seed_default_settings(db)
    rows = await db.scalars(
        select(orm.AppSetting).order_by(orm.AppSetting.category, orm.AppSetting.key)
    )
    return list(rows)


async def aset_setting(
    db: AsyncSession, key: str, value: Any, *, updated_by_id: uuid.UUID | None
) -> orm.AppSetting:
    default = DEFAULT_SETTINGS.get(key)
    if default is None:
        raise KeyError(f"Unknown setting key: {key!r}")
    row = await db.scalar(select(orm.AppSetting).where(orm.AppSetting.key == key))
    if row is None:
        row = orm.AppSetting(key=key, category=default.category, description=default.description)
        db.add(row)
    row.value = {"v": value}
    row.updated_by_id = updated_by_id
    await db.commit()
    await db.refresh(row)
    invalidate_cache(key)
    return row


async def seed_default_settings(db: AsyncSession) -> None:
    existing_keys = set(await db.scalars(select(orm.AppSetting.key)))
    missing = [key for key in DEFAULT_SETTINGS if key not in existing_keys]
    if not missing:
        return
    for key in missing:
        default = DEFAULT_SETTINGS[key]
        db.add(
            orm.AppSetting(
                key=key,
                category=default.category,
                value={"v": default.value},
                description=default.description,
            )
        )
    await db.commit()
