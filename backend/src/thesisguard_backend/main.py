"""FastAPI app assembly and startup wiring.

Run locally with: ``uvicorn thesisguard_backend.main:app --reload``
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from agents.graph import configure_agent
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from thesisguard_backend.agent_adapters import build_default_agent
from thesisguard_backend.db import initialize_local_database, session_factory
from thesisguard_backend.observability import langfuse_status, shutdown_langfuse
from thesisguard_backend.routers import alerts, analysis, auth, holdings, portfolios, theses


@asynccontextmanager
async def lifespan(app: FastAPI):
    await initialize_local_database()

    # Wires C's ThesisGuardAgent with B's DB-backed ContextProvider and
    # MCP-backed ResearchTools exactly once, per docs/api.md.
    # configure_agent() makes the module-level arun_analysis_workflow() work
    # (as docs/api.md documents); app.state.agent keeps our own reference for
    # instance-only methods C doesn't expose at module level (e.g. astructure_thesis).
    agent = build_default_agent(session_factory)
    configure_agent(agent)
    app.state.agent = agent
    try:
        yield
    finally:
        shutdown_langfuse()


app = FastAPI(title="ThesisGuard API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
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


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    agent = getattr(app.state, "agent", None)
    rag_enabled = bool(agent and agent.dependencies.retriever is not None)
    return {
        "status": "ok",
        "langfuse": langfuse_status(),
        "rag": "enabled" if rag_enabled else "disabled",
    }
