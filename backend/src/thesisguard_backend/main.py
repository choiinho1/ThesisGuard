"""FastAPI app assembly and startup wiring.

Run locally with: ``uvicorn thesisguard_backend.main:app --reload``
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

from agents.graph import configure_agent
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from thesisguard_backend import settings_service
from thesisguard_backend.agent_adapters import build_default_agent
from thesisguard_backend.config import get_settings
from thesisguard_backend.db import initialize_local_database, session_factory
from thesisguard_backend.evidence_history import refresh_all_evidence_history_files
from thesisguard_backend.observability import langfuse_status, shutdown_langfuse
from thesisguard_backend.routers import (
    admin,
    alerts,
    analysis,
    analysis_schedules,
    auth,
    holdings,
    market,
    portfolios,
    theses,
)
from thesisguard_backend.scheduler import scheduler_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    await initialize_local_database()
    await refresh_all_evidence_history_files(session_factory)
    async with session_factory() as db:
        await settings_service.seed_default_settings(db)

    # Wires C's ThesisGuardAgent with B's DB-backed ContextProvider and
    # MCP-backed ResearchTools exactly once, per docs/api.md.
    # configure_agent() makes the module-level arun_analysis_workflow() work
    # (as docs/api.md documents); app.state.agent keeps our own reference for
    # instance-only methods C doesn't expose at module level (e.g. astructure_thesis).
    # routers/analysis.py's run_analysis_and_save() calls configure_agent()
    # again with AppSettings-derived config right before each analysis run, so
    # this startup build is only what serves structure_thesis/portfolio-query
    # until the first analysis runs.
    agent = build_default_agent(session_factory)
    configure_agent(agent)
    app.state.agent = agent
    scheduler_task = None
    if get_settings().scheduler_enabled:
        scheduler_task = asyncio.create_task(scheduler_loop())
    try:
        yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            with suppress(asyncio.CancelledError):
                await scheduler_task
        shutdown_langfuse()


app = FastAPI(title="ThesisGuard API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(portfolios.router)
app.include_router(holdings.router)
app.include_router(theses.router)
app.include_router(analysis.router)
app.include_router(alerts.router)
app.include_router(analysis_schedules.router)
app.include_router(market.router)
app.include_router(admin.router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    agent = getattr(app.state, "agent", None)
    rag_enabled = bool(agent and agent.dependencies.retriever is not None)
    return {
        "status": "ok",
        "langfuse": langfuse_status(),
        "rag": "enabled" if rag_enabled else "disabled",
    }
