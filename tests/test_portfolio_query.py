from __future__ import annotations

import pytest

from agents.graph import ThesisGuardAgent
from agents.model import LangChainAnalysisModel
from agents.models import (
    EvidenceClassification,
    EvidenceImpact,
    EvidenceItem,
    EvidenceSourceType,
    PortfolioQueryAnswer,
    PortfolioQueryEvidence,
    PortfolioThesis,
    StructuredThesis,
)


def _thesis(holding_id: str = "holding-1", ticker: str = "NVDA") -> PortfolioThesis:
    return PortfolioThesis(
        holding_id=holding_id,
        ticker=ticker,
        current_weight=50,
        thesis=StructuredThesis(
            raw_input=f"{ticker}의 데이터센터 수요가 장기간 증가할 것이다.",
            main_thesis=f"{ticker} 데이터센터 수요 성장",
            key_assumptions=["고객의 AI 설비투자가 증가한다"],
        ),
    )


def _evidence(document_id: str = "doc-nvda") -> EvidenceItem:
    return EvidenceItem(
        document_id=document_id,
        source_type=EvidenceSourceType.NEWS,
        source_url=f"https://example.com/{document_id}",
        content_snippet="고객사가 다음 회계연도의 AI 설비투자 예산을 확대했습니다.",
        classification=EvidenceClassification.SUPPORT,
        impact=EvidenceImpact.HIGH,
        reason="핵심 고객의 예산 증가는 설비투자 가정을 직접 지지합니다.",
        related_assumptions=["고객의 AI 설비투자가 증가한다"],
    )


class _CapturingRunnable:
    def __init__(self, result: PortfolioQueryAnswer) -> None:
        self.result = result
        self.messages = []

    async def ainvoke(self, messages, config=None):  # type: ignore[no-untyped-def]
        del config
        self.messages = messages
        return self.result


class _ChatModel:
    def __init__(self, runnable: _CapturingRunnable | None = None) -> None:
        self.runnable = runnable
        self.calls = 0

    def with_structured_output(self, schema):  # type: ignore[no-untyped-def]
        assert schema is PortfolioQueryAnswer
        self.calls += 1
        if self.runnable is None:
            raise AssertionError("The chat model must not be invoked for a deterministic fallback")
        return self.runnable


@pytest.mark.asyncio
async def test_portfolio_query_prompt_contains_identity_grounding_and_policy_rules() -> None:
    runnable = _CapturingRunnable(
        PortfolioQueryAnswer(
            answer=" NVDA의 근거가 해당 가정을 지지합니다. ",
            evidence_document_ids=["doc-nvda", "unknown-doc", "doc-nvda"],
            limitations=["MU와 비교할 근거가 없습니다.", "MU와 비교할 근거가 없습니다."],
        )
    )
    model = LangChainAnalysisModel(_ChatModel(runnable))  # type: ignore[arg-type]
    evidence = PortfolioQueryEvidence(
        holding_id="holding-1",
        ticker="NVDA",
        thesis_id="thesis-1",
        evidence=_evidence(),
    )

    result = await model.answer_portfolio_query(
        "어떤 가정이 강화됐나요?",
        [_thesis()],
        [evidence],
    )

    prompt = runnable.messages[1].content
    assert "Treat thesis statements as investor hypotheses" in prompt
    assert "Do not recommend buying, selling, holding" in prompt
    assert '"holding_id": "holding-1"' in prompt
    assert '"ticker": "NVDA"' in prompt
    assert '"document_id": "doc-nvda"' in prompt
    assert result.answer == "NVDA의 근거가 해당 가정을 지지합니다."
    assert result.evidence_document_ids == ["doc-nvda"]
    assert result.limitations == ["MU와 비교할 근거가 없습니다."]


@pytest.mark.asyncio
async def test_portfolio_query_adds_limitation_for_legacy_evidence_without_identity() -> None:
    runnable = _CapturingRunnable(
        PortfolioQueryAnswer(
            answer="최근 근거가 설비투자 가정을 지지합니다.",
            evidence_document_ids=["doc-nvda"],
        )
    )
    model = LangChainAnalysisModel(_ChatModel(runnable))  # type: ignore[arg-type]

    result = await model.answer_portfolio_query(
        "최근 근거는 무엇인가요?",
        [_thesis()],
        [_evidence()],
    )

    assert result.evidence_document_ids == ["doc-nvda"]
    assert result.limitations == ["일부 근거에 종목 식별자가 없어 종목별 귀속이 제한됩니다."]
    prompt = runnable.messages[1].content
    assert '"holding_id": null' in prompt
    assert '"ticker": null' in prompt


@pytest.mark.asyncio
async def test_portfolio_query_returns_fallback_without_evidence_or_model_call() -> None:
    chat_model = _ChatModel()
    model = LangChainAnalysisModel(chat_model)  # type: ignore[arg-type]

    result = await model.answer_portfolio_query("공통 위험은?", [_thesis()], [])

    assert chat_model.calls == 0
    assert result.evidence_document_ids == []
    assert "검증 근거가 없어" in result.answer
    assert "외부 근거" in result.limitations[0]


@pytest.mark.asyncio
async def test_portfolio_query_returns_fallback_without_theses_or_model_call() -> None:
    chat_model = _ChatModel()
    model = LangChainAnalysisModel(chat_model)  # type: ignore[arg-type]

    result = await model.answer_portfolio_query("공통 위험은?", [], [_evidence()])

    assert chat_model.calls == 0
    assert result.evidence_document_ids == []
    assert "투자 논리가 없어" in result.answer
    assert "구조화된 Thesis" in result.limitations[0]


class _ContextProvider:
    async def load_analysis_context(self, portfolio_id: str, holding_id: str):
        raise AssertionError("Portfolio query must not load a holding analysis context")

    async def load_portfolio_theses(self, portfolio_id: str) -> list[PortfolioThesis]:
        assert portfolio_id == "portfolio-1"
        return [_thesis()]


class _ResearchTools:
    async def get_filings(self, request):
        raise AssertionError("not used")

    async def get_news(self, request):
        raise AssertionError("not used")

    async def get_macro(self, request):
        raise AssertionError("not used")


class _QueryModel:
    def __init__(self) -> None:
        self.question = ""

    async def answer_portfolio_query(self, question, portfolio_theses, evidence):
        self.question = question
        return PortfolioQueryAnswer(answer="확인했습니다.")


@pytest.mark.asyncio
async def test_agent_normalizes_and_validates_portfolio_question() -> None:
    query_model = _QueryModel()
    agent = ThesisGuardAgent(
        context_provider=_ContextProvider(),  # type: ignore[arg-type]
        research_tools=_ResearchTools(),  # type: ignore[arg-type]
        model=query_model,  # type: ignore[arg-type]
    )

    await agent.aanswer_portfolio_query(
        "portfolio-1",
        "  공통 위험은 무엇인가요?  ",
        [_evidence()],
    )
    assert query_model.question == "공통 위험은 무엇인가요?"

    with pytest.raises(ValueError, match="must not be empty"):
        await agent.aanswer_portfolio_query("portfolio-1", "   ")
    with pytest.raises(ValueError, match="at most 500"):
        await agent.aanswer_portfolio_query("portfolio-1", "가" * 501)
