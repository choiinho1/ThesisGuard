"""Field-for-field check: does B's JSON match A's frontend/types/schema.ts?

Compares the exact key sets of B's Pydantic response schemas against the
frontend TypeScript interfaces they're supposed to mirror (hardcoded below,
copied from frontend/types/schema.ts on feature/fe-schema-alignment). It also
builds one of each response with a real LangGraph run (real MCP calls, fake
DB/LLM — see check_agent_compat.py) to make sure the response actually
serializes without errors.

Run from backend/:
    PYTHONPATH="..;src" ../.venv/Scripts/python.exe scripts/check_fe_schema_compat.py
"""

from __future__ import annotations

import asyncio

from thesisguard_backend.schemas import (
    AlertResponse,
    AnalysisResultResponse,
    DashboardHoldingResponse,
    HoldingAnalysisResponse,
    HoldingResponse,
    PortfolioDashboardResponse,
    PortfolioResponse,
    ThesisResponse,
    ThesisVersionResponse,
)

# Copied from frontend/types/schema.ts (branch feature/fe-schema-alignment).
# Extra fields on the B side are fine (the frontend just won't read them);
# a MISSING field or a field the frontend expects that B doesn't send is not.
FRONTEND_INTERFACES: dict[type, set[str]] = {
    PortfolioResponse: {
        "id",
        "user_id",
        "name",
        "investment_purpose",
        "investment_horizon",
        "cash_ratio",
        "created_at",
        "updated_at",
    },
    HoldingResponse: {
        "id",
        "portfolio_id",
        "ticker",
        "company_name",
        "quantity",
        "avg_buy_price",
        "target_weight",
        "current_weight",
        "created_at",
        "updated_at",
    },
    ThesisResponse: {
        "id",
        "holding_id",
        "raw_input",
        "main_thesis",
        "key_assumptions",
        "positive_signals",
        "negative_signals",
        "key_risks",
        "confidence_score",
        "status",
        "created_at",
        "updated_at",
    },
    ThesisVersionResponse: {
        "id",
        "thesis_id",
        "version_no",
        "confidence_score",
        "status",
        "change_reason",
        "conflicting_assumptions",
        "observation_points",
        "snapshot",
        "created_at",
    },
    AnalysisResultResponse: {
        "id",
        "portfolio_id",
        "thesis_id",
        "analysis_type",
        "bull_summary",
        "bear_summary",
        "judge_summary",
        "concentration_theme",
        "concentration_score",
        "affected_holdings",
        "raw_result",
        "created_at",
    },
    AlertResponse: {
        "id",
        "user_id",
        "portfolio_id",
        "thesis_id",
        "severity",
        "title",
        "message",
        "is_sent",
        "sent_at",
        "created_at",
        # "delivery" is B-only (not in the frontend Alert type) — fine, extra field.
    },
    DashboardHoldingResponse: {
        "id",
        "portfolio_id",
        "ticker",
        "company_name",
        "quantity",
        "avg_buy_price",
        "target_weight",
        "current_weight",
        "created_at",
        "updated_at",
        "thesis",
        "latest_change",
    },
    PortfolioDashboardResponse: {
        "portfolio",
        "holdings",
        "concentration",
        "common_risks",
        "recent_alerts",
    },
    HoldingAnalysisResponse: {
        "thesis",
        "version",
        "evidence",
        "analysis_result",
        "alert",
    },
}


def check_field_sets() -> list[str]:
    problems = []
    for model, expected in FRONTEND_INTERFACES.items():
        actual = set(model.model_fields.keys())
        missing = expected - actual
        extra = actual - expected
        status = "OK" if not missing else "MISSING FIELDS"
        print(f"{model.__name__}: {status}")
        if missing:
            problems.append(f"{model.__name__} is missing fields the frontend expects: {missing}")
            print(f"  missing: {missing}")
        if extra:
            print(f"  extra (harmless): {extra}")
    return problems


async def check_live_serialization() -> None:
    print("\n=== Live serialization check (real MCP calls, fake DB/LLM) ===")
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from agents.graph import ThesisGuardAgent
    from agents.runtime import WorkflowConfig
    from check_agent_compat import FakeAnalysisModel, FakeContextProvider  # noqa: E402

    from thesisguard_backend.agent_adapters import BackendResearchTools

    agent = ThesisGuardAgent(
        context_provider=FakeContextProvider(),
        research_tools=BackendResearchTools(),
        model=FakeAnalysisModel(),
        config=WorkflowConfig(max_research_rounds=1, min_grounded_evidence=1, model_max_attempts=1),
    )
    result = await agent.arun_analysis_workflow("test-portfolio-1", "test-holding-1")

    # Build the exact same HoldingAnalysisResponse shape analysis.py returns,
    # using plain dicts instead of ORM rows (no DB available here).
    evidence = [
        {
            "id": "00000000-0000-4000-8000-000000000000",
            "thesis_id": "00000000-0000-4000-8000-000000000000",
            "document_id": item.document_id,
            "source_type": item.source_type,
            "source_url": str(item.source_url) if item.source_url else None,
            "vector_doc_id": item.vector_doc_id,
            "content_snippet": item.content_snippet,
            "classification": item.classification,
            "impact": item.impact,
            "reason": item.reason,
            "related_assumptions": item.related_assumptions,
            "published_at": item.published_at,
        }
        for item in result.evidence
    ]
    response = HoldingAnalysisResponse(
        thesis={
            "id": "00000000-0000-4000-8000-000000000000",
            "holding_id": "00000000-0000-4000-8000-000000000001",
            "raw_input": "x" * 10,
            "main_thesis": "fake",
            "key_assumptions": ["a"],
            "positive_signals": [],
            "negative_signals": [],
            "key_risks": [],
            "template_id": result.score_breakdown.template_id,
            "template_catalog_version": result.score_breakdown.template_catalog_version,
            "template_snapshot": {},
            "assumption_bindings": [],
            "score_breakdown": result.score_breakdown,
            "confidence_score": result.updated_confidence,
            "status": result.updated_status,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        },
        version={
            "id": "00000000-0000-4000-8000-000000000000",
            "thesis_id": "00000000-0000-4000-8000-000000000000",
            "version_no": 1,
            "confidence_score": result.updated_confidence,
            "status": result.updated_status,
            "change_reason": result.change_reason,
            "conflicting_assumptions": result.conflicting_assumptions,
            "observation_points": result.observation_points,
            "snapshot": {"main_thesis": "fake"},
            "created_at": "2026-01-01T00:00:00Z",
        },
        evidence=evidence,
        analysis_result={
            "id": "00000000-0000-4000-8000-000000000000",
            "portfolio_id": None,
            "thesis_id": "00000000-0000-4000-8000-000000000000",
            "analysis_type": "BULL_BEAR_JUDGE",
            "bull_summary": result.bull_summary,
            "bear_summary": result.bear_summary,
            "judge_summary": result.judge_summary,
            "concentration_theme": None,
            "concentration_score": None,
            "affected_holdings": [],
            "raw_result": result.model_dump(mode="json"),
            "created_at": "2026-01-01T00:00:00Z",
        },
        alert=None,
    )
    dumped = response.model_dump(mode="json")
    print(f"HoldingAnalysisResponse serialized OK, top-level keys: {list(dumped.keys())}")
    assert set(dumped.keys()) == FRONTEND_INTERFACES[HoldingAnalysisResponse]
    print("Top-level keys match frontend/types/schema.ts's HoldingAnalysisResponse exactly.")


async def main() -> None:
    problems = check_field_sets()
    await check_live_serialization()
    if problems:
        print("\nFAILED:")
        for p in problems:
            print(f"  - {p}")
        raise SystemExit(1)
    print("\nCOMPATIBLE: backend response schemas match frontend/types/schema.ts.")


if __name__ == "__main__":
    asyncio.run(main())
