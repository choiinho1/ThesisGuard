from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agents.graph import (
    ThesisGuardAgent,
    configure_agent,
    run_analysis_workflow,
)
from agents.models import (
    AnalysisContext,
    DebateReport,
    EvidenceAssessment,
    EvidenceClassification,
    EvidenceImpact,
    EvidenceItem,
    EvidenceSourceType,
    JudgeDecision,
    PortfolioAnalysis,
    PortfolioThesis,
    ResearchRequest,
    SourceDocument,
    StructuredThesis,
    ThesisStatus,
)
from agents.runtime import WorkflowConfig


def thesis(status: ThesisStatus = ThesisStatus.UNCHANGED) -> StructuredThesis:
    return StructuredThesis(
        raw_input="AI 데이터센터 투자가 확대되면 반도체 수요가 장기간 성장할 것이다.",
        main_thesis="AI 데이터센터 투자 확대에 따른 반도체 수요 성장",
        key_assumptions=["AI 인프라 지출 증가", "데이터센터용 반도체 수요 증가"],
        positive_signals=["클라우드 사업자 CAPEX 증가"],
        negative_signals=["CAPEX 축소"],
        key_risks=["공급 과잉"],
        confidence_score=70,
        status=status,
    )


class FakeContextProvider:
    async def load_analysis_context(self, portfolio_id: str, holding_id: str) -> AnalysisContext:
        current = PortfolioThesis(
            holding_id=holding_id,
            ticker="NVDA",
            current_weight=60,
            thesis=thesis(),
        )
        other = PortfolioThesis(
            holding_id="holding-2",
            ticker="AMD",
            current_weight=40,
            thesis=thesis(),
        )
        return AnalysisContext(
            portfolio_id=portfolio_id,
            holding_id=holding_id,
            ticker="NVDA",
            thesis=current.thesis,
            portfolio_theses=[current, other],
            evidence_history_summary="과거에는 AI CAPEX 확대 흐름이 이어졌습니다.",
            evidence_history_document_ids=["historical-filing"],
        )

    async def load_portfolio_theses(self, portfolio_id: str) -> list[PortfolioThesis]:
        context = await self.load_analysis_context(portfolio_id, "holding-1")
        return context.portfolio_theses


def document(document_id: str, source_type: EvidenceSourceType, content: str) -> SourceDocument:
    return SourceDocument(
        document_id=document_id,
        source_type=source_type,
        source_url=f"https://example.com/{document_id}",
        title=document_id,
        content=content,
        published_at=datetime.now(UTC) - timedelta(days=2),
    )


class FakeResearchTools:
    def __init__(self, *, fail_macro: bool = False, uncertain_only: bool = False) -> None:
        self.calls: list[tuple[str, int]] = []
        self.fail_macro = fail_macro
        self.uncertain_only = uncertain_only

    async def get_filings(self, request: ResearchRequest) -> list[SourceDocument]:
        self.calls.append(("filings", request.round_no))
        doc_id = "uncertain-filing" if self.uncertain_only else "support-filing"
        return [
            document(
                doc_id,
                EvidenceSourceType.SEC_FILING,
                "Data center revenue grew 120 percent.",
            )
        ]

    async def get_news(self, request: ResearchRequest) -> list[SourceDocument]:
        self.calls.append(("news", request.round_no))
        if self.uncertain_only or request.round_no == 1:
            return [
                document(
                    "uncertain-news",
                    EvidenceSourceType.NEWS,
                    "NVDA AI infrastructure outlook remains unclear.",
                )
            ]
        return [
            document(
                "contradict-news",
                EvidenceSourceType.NEWS,
                "NVDA major customers reduced CAPEX.",
            )
        ]

    async def get_macro(self, request: ResearchRequest) -> list[SourceDocument]:
        self.calls.append(("macro", request.round_no))
        if self.fail_macro:
            raise RuntimeError("macro provider unavailable")
        return []


class FakeAnalysisModel:
    def __init__(self) -> None:
        self.judge_calls = 0
        self.classify_calls = 0
        self.history_contexts: list[str] = []

    async def structure_thesis(self, raw_input: str) -> StructuredThesis:
        return thesis().model_copy(update={"raw_input": raw_input})

    async def classify_evidence(
        self,
        existing_thesis: StructuredThesis,
        source: SourceDocument,
        evidence_history_summary: str = "",
    ) -> EvidenceAssessment:
        self.classify_calls += 1
        self.history_contexts.append(evidence_history_summary)
        if source.document_id.startswith("support"):
            classification = EvidenceClassification.SUPPORT
            impact = EvidenceImpact.MEDIUM
        elif source.document_id.startswith("contradict"):
            classification = EvidenceClassification.CONTRADICT
            impact = EvidenceImpact.HIGH
        else:
            classification = EvidenceClassification.UNCERTAIN
            impact = EvidenceImpact.LOW
        return EvidenceAssessment(
            classification=classification,
            impact=impact,
            relevance_score=0.9,
            reason=f"{source.document_id} 분류",
            related_assumptions=[existing_thesis.key_assumptions[0]],
            source_excerpt=source.content,
            content_snippet=f"{source.document_id} 관련 근거 요약입니다.",
        )

    async def build_bull_report(
        self,
        existing_thesis: StructuredThesis,
        evidence: list[EvidenceItem],
        evidence_history_summary: str = "",
    ) -> DebateReport:
        self.history_contexts.append(evidence_history_summary)
        ids = [
            item.document_id
            for item in evidence
            if item.classification == EvidenceClassification.SUPPORT
        ]
        return DebateReport(summary="지지 근거 요약", evidence_document_ids=ids)

    async def build_bear_report(
        self,
        existing_thesis: StructuredThesis,
        evidence: list[EvidenceItem],
        evidence_history_summary: str = "",
    ) -> DebateReport:
        self.history_contexts.append(evidence_history_summary)
        ids = [
            item.document_id
            for item in evidence
            if item.classification == EvidenceClassification.CONTRADICT
        ]
        return DebateReport(summary="반박 근거 요약", evidence_document_ids=ids)

    async def judge(
        self,
        existing_thesis: StructuredThesis,
        evidence: list[EvidenceItem],
        bull_report: DebateReport,
        bear_report: DebateReport,
        evidence_history_summary: str = "",
    ) -> JudgeDecision:
        self.judge_calls += 1
        self.history_contexts.append(evidence_history_summary)
        return JudgeDecision(
            updated_confidence=45,
            updated_status=ThesisStatus.STRONGLY_WEAKENED,
            change_reason="반박 근거의 영향도가 더 큽니다.",
            judge_summary="고객 CAPEX 축소가 핵심 전제를 훼손합니다.",
            conflicting_assumptions=[existing_thesis.key_assumptions[0]],
            observation_points=["다음 분기 고객 CAPEX"],
        )

    async def analyze_portfolio(self, portfolio_theses: list[PortfolioThesis]) -> PortfolioAnalysis:
        return PortfolioAnalysis(
            has_concentration_risk=True,
            summary="AI CAPEX 테마에 집중되어 있습니다.",
            themes=[
                {
                    "theme": "AI CAPEX",
                    "concentration_score": 100,
                    "affected_holdings": [item.holding_id for item in portfolio_theses],
                    "shared_assumptions": ["AI 인프라 지출 증가"],
                }
            ],
        )


class FailingJudgeModel(FakeAnalysisModel):
    async def judge(
        self,
        existing_thesis: StructuredThesis,
        evidence: list[EvidenceItem],
        bull_report: DebateReport,
        bear_report: DebateReport,
        evidence_history_summary: str = "",
    ) -> JudgeDecision:
        self.judge_calls += 1
        raise RuntimeError("temporary model failure")


class FailingPortfolioModel(FakeAnalysisModel):
    async def analyze_portfolio(self, portfolio_theses: list[PortfolioThesis]) -> PortfolioAnalysis:
        raise RuntimeError("portfolio model failure")


@pytest.mark.asyncio
async def test_full_workflow_researches_again_and_returns_db_ready_result() -> None:
    tools = FakeResearchTools()
    model = FakeAnalysisModel()
    agent = ThesisGuardAgent(
        context_provider=FakeContextProvider(),
        research_tools=tools,
        model=model,
        config=WorkflowConfig(max_research_rounds=2, min_grounded_evidence=2),
    )

    result = await agent.arun_analysis_workflow("portfolio-1", "holding-1")

    assert result.research_rounds == 2
    assert {item.document_id for item in result.evidence} == {
        "support-filing",
        "uncertain-news",
        "contradict-news",
    }
    assert result.updated_status == ThesisStatus.STRONGLY_WEAKENED
    assert result.alert_decision.severity == "MAJOR"
    assert result.alert_decision.delivery == "IMMEDIATE"
    assert result.concentration.has_concentration_risk is True
    assert model.judge_calls == 1
    assert model.classify_calls == 3
    assert model.history_contexts
    assert set(model.history_contexts) == {"과거에는 AI CAPEX 확대 흐름이 이어졌습니다."}
    assert set(tools.calls) == {
        ("filings", 1),
        ("filings", 2),
        ("news", 1),
        ("news", 2),
        ("macro", 1),
        ("macro", 2),
    }


@pytest.mark.asyncio
async def test_portfolio_model_failure_is_not_silently_hidden() -> None:
    agent = ThesisGuardAgent(
        context_provider=FakeContextProvider(),
        research_tools=FakeResearchTools(),
        model=FailingPortfolioModel(),
        config=WorkflowConfig(max_research_rounds=1, min_grounded_evidence=1),
    )

    with pytest.raises(RuntimeError, match="portfolio model failure"):
        await agent.arun_analysis_workflow("portfolio-1", "holding-1")


@pytest.mark.asyncio
async def test_no_directional_evidence_keeps_thesis_unchanged_without_llm_judgment() -> None:
    model = FakeAnalysisModel()
    agent = ThesisGuardAgent(
        context_provider=FakeContextProvider(),
        research_tools=FakeResearchTools(uncertain_only=True),
        model=model,
        config=WorkflowConfig(max_research_rounds=1, min_grounded_evidence=1),
    )

    result = await agent.arun_analysis_workflow("portfolio-1", "holding-1")

    assert result.updated_status == ThesisStatus.UNCHANGED
    assert result.updated_confidence == 70
    assert result.alert_decision.should_send is False
    assert model.judge_calls == 0


@pytest.mark.asyncio
async def test_one_source_failure_does_not_abort_the_analysis() -> None:
    agent = ThesisGuardAgent(
        context_provider=FakeContextProvider(),
        research_tools=FakeResearchTools(fail_macro=True),
        model=FakeAnalysisModel(),
        config=WorkflowConfig(max_research_rounds=2, min_grounded_evidence=2),
    )

    result = await agent.arun_analysis_workflow("portfolio-1", "holding-1")

    assert result.updated_status == ThesisStatus.STRONGLY_WEAKENED
    assert any(item.source_type == EvidenceSourceType.SEC_FILING for item in result.evidence)


@pytest.mark.asyncio
async def test_judge_failure_retries_then_keeps_existing_thesis() -> None:
    model = FailingJudgeModel()
    agent = ThesisGuardAgent(
        context_provider=FakeContextProvider(),
        research_tools=FakeResearchTools(),
        model=model,
        config=WorkflowConfig(
            max_research_rounds=2,
            min_grounded_evidence=2,
            model_max_attempts=2,
        ),
    )

    result = await agent.arun_analysis_workflow("portfolio-1", "holding-1")

    assert model.judge_calls == 2
    assert result.updated_status == ThesisStatus.UNCHANGED
    assert result.updated_confidence == 70
    assert result.alert_decision.should_send is False


def test_sync_team_contract_entrypoint() -> None:
    agent = ThesisGuardAgent(
        context_provider=FakeContextProvider(),
        research_tools=FakeResearchTools(),
        model=FakeAnalysisModel(),
        config=WorkflowConfig(max_research_rounds=2, min_grounded_evidence=2),
    )
    configure_agent(agent)

    result = run_analysis_workflow("portfolio-1", "holding-1")

    assert result.portfolio_id == "portfolio-1"
    assert result.holding_id == "holding-1"
    assert result.research_rounds == 2
