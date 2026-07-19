"""Admin console: live-tunable parameters, ops overview, scenario testing, Q&A logs.

Everything here requires ``AdminUser`` (role == UserRole.ADMIN, see deps.py).
There is no self-service signup path to admin — see scripts/promote_admin.py.
"""

from __future__ import annotations

import uuid

import httpx
from agents.evaluation.metrics import (
    portfolio_query_citation_precision,
    portfolio_query_citation_recall,
    portfolio_query_limitation_recall,
)
from agents.models import PortfolioQueryEvidence, PortfolioThesis
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from thesisguard_backend import models as orm
from thesisguard_backend import settings_service
from thesisguard_backend.config import get_settings
from thesisguard_backend.deps import AdminUser, Agent, DbSession
from thesisguard_backend.observability import (
    LangfuseTraceSummary,
    alist_recent_traces,
    langfuse_status,
)
from thesisguard_backend.schemas import (
    AdminHealthResponse,
    AdminScheduleOverviewResponse,
    AppSettingResponse,
    AppSettingUpdateRequest,
    EvalRunResponse,
    EvalScenarioCreateRequest,
    EvalScenarioResponse,
    EvalScenarioUpdateRequest,
    LangfuseTraceResponse,
    QaLogResponse,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# --------------------------------------------------------------- Settings
@router.get("/settings", response_model=list[AppSettingResponse])
async def list_settings(db: DbSession, _admin: AdminUser) -> list[orm.AppSetting]:
    return await settings_service.alist_settings(db)


@router.put("/settings/{key}", response_model=AppSettingResponse)
async def update_setting(
    key: str, payload: AppSettingUpdateRequest, db: DbSession, admin: AdminUser
) -> orm.AppSetting:
    try:
        return await settings_service.aset_setting(db, key, payload.value, updated_by_id=admin.id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


# ------------------------------------------------------------------- Ops
@router.get("/schedules", response_model=list[AdminScheduleOverviewResponse])
async def list_schedules(db: DbSession, _admin: AdminUser) -> list[AdminScheduleOverviewResponse]:
    rows = list(
        await db.execute(
            select(orm.AnalysisSchedule, orm.Holding, orm.User)
            .join(orm.Holding, orm.Holding.id == orm.AnalysisSchedule.holding_id)
            .join(orm.Portfolio, orm.Portfolio.id == orm.Holding.portfolio_id)
            .join(orm.User, orm.User.id == orm.Portfolio.user_id)
            .order_by(orm.AnalysisSchedule.next_run_at)
        )
    )
    overview: list[AdminScheduleOverviewResponse] = []
    for schedule, holding, user in rows:
        latest_run = await db.scalar(
            select(orm.ScheduledAnalysisRun)
            .where(orm.ScheduledAnalysisRun.schedule_id == schedule.id)
            .order_by(orm.ScheduledAnalysisRun.created_at.desc())
            .limit(1)
        )
        overview.append(
            AdminScheduleOverviewResponse(
                schedule_id=schedule.id,
                holding_id=holding.id,
                ticker=holding.ticker,
                user_email=user.email,
                enabled=schedule.enabled,
                next_run_at=schedule.next_run_at,
                last_run_at=schedule.last_run_at,
                latest_run_status=latest_run.status.value if latest_run else None,
                latest_run_error=latest_run.error_message if latest_run else None,
            )
        )
    return overview


@router.get("/health", response_model=AdminHealthResponse)
async def admin_health(db: DbSession, _admin: AdminUser) -> AdminHealthResponse:
    settings = get_settings()
    database_status = "ok"
    try:
        await db.execute(select(1))
    except Exception:  # noqa: BLE001 — surfaced as a status string, not a crash
        database_status = "unreachable"
    return AdminHealthResponse(
        database=database_status,
        llm_provider=settings.llm_provider,
        rag_enabled=settings.rag_enabled,
        langfuse=langfuse_status(),
        langfuse_base_url=settings.langfuse_base_url,
        scheduler_enabled=settings.scheduler_enabled,
        scheduler_poll_seconds=await settings_service.aget_setting(db, "scheduler.poll_seconds"),
    )


@router.get("/langfuse/traces", response_model=list[LangfuseTraceResponse])
async def list_langfuse_traces(_admin: AdminUser, limit: int = 20) -> list[LangfuseTraceSummary]:
    try:
        return await alist_recent_traces(limit=limit)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Langfuse 조회에 실패했습니다: {exc}"
        ) from exc


# -------------------------------------------------------------- Scenarios
@router.get("/scenarios", response_model=list[EvalScenarioResponse])
async def list_scenarios(db: DbSession, _admin: AdminUser) -> list[orm.EvalScenario]:
    return list(
        await db.scalars(select(orm.EvalScenario).order_by(orm.EvalScenario.created_at.desc()))
    )


@router.post("/scenarios", response_model=EvalScenarioResponse, status_code=status.HTTP_201_CREATED)
async def create_scenario(
    payload: EvalScenarioCreateRequest, db: DbSession, admin: AdminUser
) -> orm.EvalScenario:
    scenario = orm.EvalScenario(**payload.model_dump(), created_by_id=admin.id)
    db.add(scenario)
    await db.commit()
    await db.refresh(scenario)
    return scenario


@router.put("/scenarios/{scenario_id}", response_model=EvalScenarioResponse)
async def update_scenario(
    scenario_id: uuid.UUID, payload: EvalScenarioUpdateRequest, db: DbSession, _admin: AdminUser
) -> orm.EvalScenario:
    scenario = await db.get(orm.EvalScenario, scenario_id)
    if scenario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "시나리오를 찾을 수 없습니다.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(scenario, field, value)
    await db.commit()
    await db.refresh(scenario)
    return scenario


@router.delete("/scenarios/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scenario(scenario_id: uuid.UUID, db: DbSession, _admin: AdminUser) -> None:
    scenario = await db.get(orm.EvalScenario, scenario_id)
    if scenario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "시나리오를 찾을 수 없습니다.")
    await db.delete(scenario)
    await db.commit()


async def _run_portfolio_qa_scenario(
    scenario: orm.EvalScenario, agent, settings_snapshot: dict
) -> dict:
    """Run one portfolio_qa scenario against the live model, no DB portfolio needed.

    Mirrors agents/evaluation/portfolio_qa.py's PortfolioQABenchmarkCase shape:
    context_snapshot holds ``portfolio_theses``/``evidence`` fixtures directly,
    so this is a self-contained regression check independent of any real
    portfolio — exactly what an admin editing scoring/LLM settings needs to
    "test before it's live" (mentoring feedback), without needing to touch
    real user data.
    """

    portfolio_theses = [
        PortfolioThesis.model_validate(item)
        for item in scenario.context_snapshot.get("portfolio_theses", [])
    ]
    evidence = [
        PortfolioQueryEvidence.model_validate(item)
        for item in scenario.context_snapshot.get("evidence", [])
    ]
    answer = await agent.dependencies.model.answer_portfolio_query(
        scenario.question, portfolio_theses, evidence
    )
    allowed_document_ids = {item.evidence.document_id for item in evidence}
    metrics = {
        "citation_precision": portfolio_query_citation_precision(
            allowed_document_ids, answer.evidence_document_ids
        ),
        "citation_recall": portfolio_query_citation_recall(
            set(scenario.expected_document_ids), answer.evidence_document_ids
        ),
        "limitation_recall": portfolio_query_limitation_recall(
            set(scenario.required_keywords), answer.limitations
        ),
        "forbidden_term_hits": sum(
            term.casefold() in answer.answer.casefold() for term in scenario.forbidden_terms
        ),
        "answer": answer.answer,
    }
    return metrics


@router.post("/scenarios/{scenario_id}/run", response_model=EvalRunResponse)
async def run_scenario(
    scenario_id: uuid.UUID, db: DbSession, admin: AdminUser, agent: Agent
) -> orm.EvalRun:
    scenario = await db.get(orm.EvalScenario, scenario_id)
    if scenario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "시나리오를 찾을 수 없습니다.")
    settings_snapshot = await settings_service.aget_settings_snapshot(db)
    run = orm.EvalRun(
        scenario_id=scenario.id,
        triggered_by_id=admin.id,
        settings_snapshot=settings_snapshot,
        status=orm.EvalRunStatus.RUNNING,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    try:
        metrics = await _run_portfolio_qa_scenario(scenario, agent, settings_snapshot)
    except Exception as exc:  # noqa: BLE001 — persist the failure for the admin UI
        run.status = orm.EvalRunStatus.FAILED
        run.error_message = str(exc)[:2000]
    else:
        run.status = orm.EvalRunStatus.SUCCEEDED
        run.metrics = metrics
    await db.commit()
    await db.refresh(run)
    return run


@router.post("/scenarios/run-all", response_model=list[EvalRunResponse])
async def run_all_scenarios(db: DbSession, admin: AdminUser, agent: Agent) -> list[orm.EvalRun]:
    scenarios = list(
        await db.scalars(select(orm.EvalScenario).where(orm.EvalScenario.is_active.is_(True)))
    )
    return [await run_scenario(scenario.id, db, admin, agent) for scenario in scenarios]


@router.post("/scenarios/import-legacy", response_model=list[EvalScenarioResponse])
async def import_legacy_scenarios(db: DbSession, admin: AdminUser) -> list[orm.EvalScenario]:
    """One-time import of agents/evaluation/datasets/portfolio_qa_v1.json into EvalScenario rows."""

    from agents.evaluation.portfolio_qa import load_portfolio_qa_cases

    existing_names = set(await db.scalars(select(orm.EvalScenario.name)))
    created: list[orm.EvalScenario] = []
    for case in load_portfolio_qa_cases():
        if case.case_id in existing_names:
            continue
        scenario = orm.EvalScenario(
            name=case.case_id,
            category="portfolio_qa",
            question=case.question,
            context_snapshot={
                "portfolio_theses": [
                    thesis.model_dump(mode="json") for thesis in case.portfolio_theses
                ],
                "evidence": [item.model_dump(mode="json") for item in case.evidence],
            },
            expected_document_ids=case.expected_document_ids,
            required_keywords=case.required_limitation_keywords,
            forbidden_terms=case.forbidden_answer_terms,
            created_by_id=admin.id,
        )
        db.add(scenario)
        created.append(scenario)
    await db.commit()
    for scenario in created:
        await db.refresh(scenario)
    return created


# --------------------------------------------------------------- QA logs
@router.get("/qa-logs", response_model=list[QaLogResponse])
async def list_qa_logs(
    db: DbSession,
    _admin: AdminUser,
    limit: int = 50,
    offset: int = 0,
    user_id: uuid.UUID | None = None,
    portfolio_id: uuid.UUID | None = None,
) -> list[QaLogResponse]:
    query = select(orm.QaLog, orm.User.email).join(orm.User, orm.User.id == orm.QaLog.user_id)
    if user_id is not None:
        query = query.where(orm.QaLog.user_id == user_id)
    if portfolio_id is not None:
        query = query.where(orm.QaLog.portfolio_id == portfolio_id)
    query = query.order_by(orm.QaLog.created_at.desc()).limit(limit).offset(offset)
    rows = list(await db.execute(query))
    return [
        QaLogResponse(
            id=log.id,
            user_id=log.user_id,
            user_email=email,
            portfolio_id=log.portfolio_id,
            question=log.question,
            answer=log.answer,
            evidence_document_ids=log.evidence_document_ids or [],
            created_at=log.created_at,
        )
        for log, email in rows
    ]
