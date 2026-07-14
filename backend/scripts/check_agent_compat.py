"""Integration smoke test: does B's backend really work with C's agents package?

Runs the REAL agents.graph.ThesisGuardAgent (real LangGraph, real
BackendResearchTools hitting real SEC/News/FRED/stooq endpoints) with only
the DB (ContextProvider) and the LLM (AnalysisModel) swapped for fakes, so
this needs no Postgres and no OpenAI key. If this script completes and
prints a valid ThesisAnalysisResult, B and C are structurally compatible.

Run from backend/ with the check_agent_compat venv set up:
    PYTHONPATH="..;src" ../.venv/Scripts/python.exe scripts/check_agent_compat.py
"""

from __future__ import annotations

import asyncio

from agents.graph import ThesisGuardAgent
from agents.models import (
    AnalysisContext,
    DebateReport,
    EvidenceAssessment,
    EvidenceClassification,
    EvidenceImpact,
    JudgeDecision,
    PortfolioAnalysis,
    PortfolioQueryAnswer,
    StructuredThesis,
    ThesisStatus,
)
from agents.runtime import WorkflowConfig

from thesisguard_backend.agent_adapters import BackendResearchTools
from thesisguard_backend.mcp_tools import macro, market, news, sec


class FakeContextProvider:
    """Stands in for BackendContextProvider — avoids needing Postgres."""

    async def load_analysis_context(self, portfolio_id: str, holding_id: str) -> AnalysisContext:
        thesis = StructuredThesis(
            raw_input="NVDA is well positioned as Hyperscaler AI capex keeps growing and "
            "demand for its GPUs stays strong across data center customers.",
            main_thesis=(
                "NVIDIA benefits from continued AI infrastructure investment by Hyperscalers."
            ),
            key_assumptions=["Hyperscaler AI capex keeps growing"],
            positive_signals=[],
            negative_signals=[],
            key_risks=["Custom ASIC competition erodes share"],
            confidence_score=70,
            status=ThesisStatus.UNCHANGED,
        )
        return AnalysisContext(
            portfolio_id=portfolio_id,
            holding_id=holding_id,
            ticker="NVDA",
            thesis=thesis,
            portfolio_theses=[],
        )

    async def load_portfolio_theses(self, portfolio_id: str) -> list:
        return []


class FakeAnalysisModel:
    """Stands in for LangChainAnalysisModel — avoids needing an OpenAI key."""

    async def structure_thesis(self, raw_input: str) -> StructuredThesis:
        return StructuredThesis(
            raw_input=raw_input,
            main_thesis="fake structured thesis",
            key_assumptions=["fake assumption"],
            confidence_score=50,
            status=ThesisStatus.UNCHANGED,
        )

    async def classify_evidence(self, thesis, document) -> EvidenceAssessment:
        return EvidenceAssessment(
            classification=EvidenceClassification.NEUTRAL,
            impact=EvidenceImpact.LOW,
            relevance_score=0.2,
            reason="fake classification — real data, fake LLM judgement",
            related_assumptions=[],
            source_excerpt=(document.content[:80] or "n/a"),
            content_snippet="실제 자료를 사용한 테스트용 한글 근거 요약입니다.",
        )

    async def build_bull_report(self, thesis, evidence) -> DebateReport:
        return DebateReport(summary="fake bull case")

    async def build_bear_report(self, thesis, evidence) -> DebateReport:
        return DebateReport(summary="fake bear case")

    async def judge(self, thesis, evidence, bull_report, bear_report) -> JudgeDecision:
        return JudgeDecision(
            updated_confidence=thesis.confidence_score,
            updated_status=ThesisStatus.UNCHANGED,
            change_reason="fake judge — no real evidence classification happened",
            judge_summary="fake judge summary",
        )

    async def analyze_portfolio(self, portfolio_theses) -> PortfolioAnalysis:
        return PortfolioAnalysis()

    async def answer_portfolio_query(
        self, question, portfolio_theses, evidence
    ) -> PortfolioQueryAnswer:
        return PortfolioQueryAnswer(answer="fake answer", evidence_document_ids=[], limitations=[])


async def check_real_mcp_tools() -> None:
    print("=== 1) Real MCP tool calls (no fakes here) ===")
    filings = await sec.get_filings("NVDA", limit=2)
    print(f"SEC filings for NVDA: {len(filings)} found")
    for f in filings:
        print(f"  - {f.form} filed {f.filed_at} -> {f.url}")

    news_items = await news.get_news("NVDA", limit=3)
    print(f"News for NVDA: {len(news_items)} found")
    for n in news_items[:2]:
        print(f"  - {n.title!r} ({n.source})")

    rate = await macro.get_interest_rate()
    yield_ = await macro.get_treasury_yield()
    cpi = await macro.get_cpi()
    print(f"Macro: fed funds={rate}, 10y yield={yield_}, cpi={cpi}")

    price = await market.get_price("NVDA")
    print(f"NVDA latest price: {price}")
    print()


async def check_full_graph() -> None:
    print("=== 2) Full ThesisGuardAgent.arun_analysis_workflow() with real research tools ===")
    agent = ThesisGuardAgent(
        context_provider=FakeContextProvider(),
        research_tools=BackendResearchTools(),  # real SEC/News/Macro calls
        model=FakeAnalysisModel(),
        config=WorkflowConfig(max_research_rounds=1, min_grounded_evidence=1, model_max_attempts=1),
    )
    result = await agent.arun_analysis_workflow("test-portfolio-1", "test-holding-1")
    print("ThesisAnalysisResult produced successfully:")
    print(f"  ticker={result.ticker}")
    print(f"  evidence collected: {len(result.evidence)}")
    print(
        f"  updated_status={result.updated_status}, updated_confidence={result.updated_confidence}"
    )
    print(f"  alert_decision={result.alert_decision}")
    print(f"  research_rounds={result.research_rounds}")

    # Prove B can actually persist this shape (build the ORM rows without a real DB session).
    from thesisguard_backend import models as orm

    thesis_version = orm.ThesisVersion(
        thesis_id=None,
        version_no=1,
        confidence_score=result.updated_confidence,
        status=result.updated_status,
        change_reason=result.change_reason,
        conflicting_assumptions=result.conflicting_assumptions,
        observation_points=result.observation_points,
        snapshot={},
    )
    evidence_rows = [
        orm.Evidence(
            thesis_id=None,
            document_id=item.document_id,
            source_type=item.source_type,
            source_url=str(item.source_url) if item.source_url else None,
            vector_doc_id=item.vector_doc_id,
            content_snippet=item.content_snippet,
            classification=item.classification,
            impact=item.impact,
            reason=item.reason,
            related_assumptions=item.related_assumptions,
            published_at=item.published_at,
        )
        for item in result.evidence
    ]
    print(
        f"  -> mapped into {1 + len(evidence_rows)} ORM row(s) "
        f"(1 ThesisVersion + {len(evidence_rows)} Evidence) with no type errors"
    )
    print()
    print("COMPATIBLE: agents/ and backend/ work together end to end.")


async def main() -> None:
    await check_real_mcp_tools()
    await check_full_graph()


if __name__ == "__main__":
    asyncio.run(main())
