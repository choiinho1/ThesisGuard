from __future__ import annotations

from datetime import UTC, datetime

import pytest

from thesisguard_agent.models import (
    AnalysisContext,
    DebateReport,
    EvidenceAssessment,
    EvidenceClassification,
    EvidenceItem,
    JudgeDecision,
    PortfolioAnalysis,
    PortfolioThesis,
    ResearchRequest,
    SourceDocument,
    SourceType,
    StructuredThesis,
    ThesisStatus,
)
from thesisguard_agent.workflow import ThesisGuardAgent, WorkflowConfig


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
    async def load_analysis_context(
        self, portfolio_id: str, holding_id: str
    ) -> AnalysisContext:
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
        )


def document(document_id: str, source_type: SourceType, content: str) -> SourceDocument:
    return SourceDocument(
        document_id=document_id,
        source_type=source_type,
        source_url=f"https://example.com/{document_id}",
        title=document_id,
        content=content,
        published_at=datetime(2026, 7, 12, tzinfo=UTC),
    )


class FakeResearchTools:
    def __init__(self, *, fail_macro: bool = False, uncertain_only: bool = False) -> None:
        self.calls: list[tuple[str, int]] = []
        self.fail_macro = fail_macro
        self.uncertain_only = uncertain_only

    async def get_filings(self, request: ResearchRequest) -> list[SourceDocument]:
        self.calls.append(("filings", request.round_no))
        doc_id = "uncertain-filing" if self.uncertain_only else "support-filing"
        return [document(doc_id, SourceType.FILING, "Data center revenue grew 120 percent.")]

    async def get_news(self, request: ResearchRequest) -> list[SourceDocument]:
        self.calls.append(("news", request.round_no))
        if self.uncertain_only or request.round_no == 1:
            return [document("uncertain-news", SourceType.NEWS, "The outlook remains unclear.")]
        return [document("contradict-news", SourceType.NEWS, "Major customers reduced CAPEX.")]

    async def get_macro(self, request: ResearchRequest) -> list[SourceDocument]:
        self.calls.append(("macro", request.round_no))
        if self.fail_macro:
            raise RuntimeError("macro provider unavailable")
        return []


class FakeAnalysisModel:
    def __init__(self) -> None:
        self.judge_calls = 0

    async def structure_thesis(self, raw_input: str) -> StructuredThesis:
        return thesis().model_copy(update={"raw_input": raw_input})

    async def classify_evidence(
        self, existing_thesis: StructuredThesis, source: SourceDocument
    ) -> EvidenceAssessment:
        if source.document_id.startswith("support"):
            classification = EvidenceClassification.SUPPORT
            impact = 0.7
        elif source.document_id.startswith("contradict"):
            classification = EvidenceClassification.CONTRADICT
            impact = 0.9
        else:
            classification = EvidenceClassification.UNCERTAIN
            impact = 0.1
        return EvidenceAssessment(
            classification=classification,
            impact=impact,
            reason=f"{source.document_id} 분류",
            related_assumptions=[existing_thesis.key_assumptions[0]],
            content_snippet=source.content,
        )

    async def build_bull_report(
        self, existing_thesis: StructuredThesis, evidence: list[EvidenceItem]
    ) -> DebateReport:
        ids = [
            item.document_id
            for item in evidence
            if item.classification == EvidenceClassification.SUPPORT
        ]
        return DebateReport(summary="지지 근거 요약", evidence_document_ids=ids)

    async def build_bear_report(
        self, existing_thesis: StructuredThesis, evidence: list[EvidenceItem]
    ) -> DebateReport:
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
    ) -> JudgeDecision:
        self.judge_calls += 1
        return JudgeDecision(
            updated_confidence=45,
            updated_status=ThesisStatus.STRONGLY_WEAKENED,
            change_reason="반박 근거의 영향도가 더 큽니다.",
            judge_summary="고객 CAPEX 축소가 핵심 전제를 훼손합니다.",
            conflicting_assumptions=[existing_thesis.key_assumptions[0]],
            observation_points=["다음 분기 고객 CAPEX"],
        )

    async def analyze_concentration(
        self, portfolio_theses: list[PortfolioThesis]
    ) -> PortfolioAnalysis:
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
    ) -> JudgeDecision:
        self.judge_calls += 1
        raise RuntimeError("temporary model failure")


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

    result = await agent.run_analysis_workflow("portfolio-1", "holding-1")

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
    assert set(tools.calls) == {
        ("filings", 1),
        ("filings", 2),
        ("news", 1),
        ("news", 2),
        ("macro", 1),
        ("macro", 2),
    }


@pytest.mark.asyncio
async def test_no_directional_evidence_keeps_thesis_unchanged_without_llm_judgment() -> None:
    model = FakeAnalysisModel()
    agent = ThesisGuardAgent(
        context_provider=FakeContextProvider(),
        research_tools=FakeResearchTools(uncertain_only=True),
        model=model,
        config=WorkflowConfig(max_research_rounds=1, min_grounded_evidence=1),
    )

    result = await agent.run_analysis_workflow("portfolio-1", "holding-1")

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

    result = await agent.run_analysis_workflow("portfolio-1", "holding-1")

    assert result.updated_status == ThesisStatus.STRONGLY_WEAKENED
    assert any(item.source_type == SourceType.FILING for item in result.evidence)


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

    result = await agent.run_analysis_workflow("portfolio-1", "holding-1")

    assert model.judge_calls == 2
    assert result.updated_status == ThesisStatus.UNCHANGED
    assert result.updated_confidence == 70
    assert result.alert_decision.should_send is False
