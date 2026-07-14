from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.model import LangChainAnalysisModel
from agents.models import (
    AssumptionAssessment,
    AssumptionFinding,
    EvidenceClassification,
    EvidenceImpact,
    EvidenceModelOutput,
    EvidenceSourceType,
    SourceDocument,
    StructuredThesis,
)
from agents.nodes.evidence import classify_evidence
from agents.runtime import AgentDependencies, WorkflowConfig
from agents.sanitization import safe_source_snippet, sanitize_source_text


def test_sanitize_source_text_removes_html_entities_and_markdown_link_target() -> None:
    raw = (
        '[<a href="https://news.example/article" target="_blank">'
        "애플의 현금 흐름 전망</a>&nbsp;](https://news.example/article)"
    )

    assert sanitize_source_text(raw) == "애플의 현금 흐름 전망"


def test_safe_source_snippet_uses_clean_title_when_body_has_no_visible_text() -> None:
    assert (
        safe_source_snippet("<script>ignore()</script>", "<b>Apple 실적 전망</b>")
        == "Apple 실적 전망"
    )


class _InvalidCitationModel(LangChainAnalysisModel):
    def __init__(self) -> None:
        pass

    async def _invoke(self, schema, task):  # type: ignore[no-untyped-def]
        del schema, task
        return EvidenceModelOutput(
            classification=EvidenceClassification.SUPPORT,
            impact=EvidenceImpact.HIGH,
            relevance_score=0.9,
            reason="모델이 만든 검증 불가능한 인용문",
            source_passage_indices=[999],
            content_snippet="애플의 현금 흐름이 성장한다는 근거입니다.",
        )


@pytest.mark.asyncio
async def test_model_citation_fallback_returns_sanitized_uncertain_snippet() -> None:
    thesis = StructuredThesis(
        raw_input="애플의 현금 흐름이 장기적으로 성장할 것이라는 투자 논리입니다.",
        main_thesis="애플의 장기 현금 흐름 성장",
        key_assumptions=["서비스 매출 성장"],
    )
    document = SourceDocument(
        document_id="news-1",
        source_type=EvidenceSourceType.NEWS,
        source_url="https://news.example/article",
        title="Apple 전망",
        content='<a href="https://news.example/article">애플의 현금 흐름 전망</a>&nbsp;',
    )

    result = await _InvalidCitationModel().classify_evidence(thesis, document)

    assert result.classification == EvidenceClassification.UNCERTAIN
    assert result.impact == EvidenceImpact.LOW
    assert result.content_snippet == "원문 구간을 검증할 수 없어 근거 요약을 제공하지 않습니다."
    assert result.source_excerpt == "애플의 현금 흐름 전망"
    assert "<a" not in result.content_snippet


class _LongKoreanSummaryModel(LangChainAnalysisModel):
    def __init__(self) -> None:
        pass

    async def _invoke(self, schema, task):  # type: ignore[no-untyped-def]
        del schema, task
        return EvidenceModelOutput(
            classification=EvidenceClassification.SUPPORT,
            impact=EvidenceImpact.MEDIUM,
            relevance_score=0.9,
            reason="서비스 매출 성장 근거",
            source_passage_indices=[0],
            content_snippet="가" * 500,
        )


@pytest.mark.asyncio
async def test_model_summary_is_korean_and_limited_to_500_characters() -> None:
    thesis = StructuredThesis(
        raw_input="애플의 현금 흐름이 장기적으로 성장할 것이라는 투자 논리입니다.",
        main_thesis="애플의 장기 현금 흐름 성장",
        key_assumptions=["서비스 매출 성장"],
    )
    document = SourceDocument(
        document_id="news-summary",
        source_type=EvidenceSourceType.NEWS,
        source_url="https://news.example/summary",
        title="Apple 전망",
        content="애플의 현금 흐름 전망",
    )

    result = await _LongKoreanSummaryModel().classify_evidence(thesis, document)

    assert len(result.content_snippet) == 500
    assert any("가" <= character <= "힣" for character in result.content_snippet)


class _MultiplePassageModel(LangChainAnalysisModel):
    def __init__(self) -> None:
        pass

    async def _invoke(self, schema, task):  # type: ignore[no-untyped-def]
        del schema, task
        return EvidenceModelOutput(
            classification=EvidenceClassification.SUPPORT,
            impact=EvidenceImpact.HIGH,
            relevance_score=0.95,
            reason="매출과 이익률이 함께 개선됐습니다.",
            source_passage_indices=[0, 1],
            content_snippet=(
                "최근 분기 서비스 매출이 20% 증가했고 영업이익률도 개선됐습니다. "
                "두 지표의 동반 개선은 서비스 성장과 현금 흐름 확대라는 핵심 전제를 지지합니다."
            ),
        )


@pytest.mark.asyncio
async def test_model_can_ground_detailed_summary_in_multiple_passages() -> None:
    thesis = StructuredThesis(
        raw_input="서비스 매출 성장으로 장기 현금 흐름이 확대될 것이라는 투자 논리입니다.",
        main_thesis="서비스 성장에 따른 현금 흐름 확대",
        key_assumptions=["서비스 매출 성장"],
    )
    document = SourceDocument(
        document_id="multi-passage",
        source_type=EvidenceSourceType.EARNINGS,
        source_url="https://example.com/earnings",
        title="분기 실적",
        content=(
            "서비스 매출이 최근 분기에 20% 증가했습니다. " + "매출 세부 설명 " * 35 + ". "
            "영업이익률이 전년 동기보다 개선됐습니다. " + "이익률 세부 설명 " * 35 + "."
        ),
    )

    result = await _MultiplePassageModel().classify_evidence(thesis, document)

    assert result.classification == EvidenceClassification.SUPPORT
    assert "서비스 매출이" in result.source_excerpt
    assert "영업이익률이" in result.source_excerpt
    assert "\n" in result.source_excerpt


class _CompetitorSignalModel(LangChainAnalysisModel):
    def __init__(self) -> None:
        pass

    async def _invoke(self, schema, task):  # type: ignore[no-untyped-def]
        del schema, task
        return EvidenceModelOutput(
            classification=EvidenceClassification.NEUTRAL,
            impact=EvidenceImpact.LOW,
            relevance_score=0.2,
            reason="주가 하락 기사입니다.",
            assumption_findings=[
                AssumptionFinding(
                    assumption="경쟁자 없음",
                    assessment=AssumptionAssessment.CONTRADICT,
                    impact=EvidenceImpact.MEDIUM,
                    relevance_score=0.9,
                    reasoning="Meta가 경쟁 예측시장 앱을 개발 중이라고 보도했습니다.",
                    source_passage_indices=[0],
                )
            ],
            source_passage_indices=[0],
            content_snippet=(
                "Meta가 Robinhood와 경쟁할 수 있는 예측시장 앱을 개발 중이라고 보도됐습니다. "
                "출시 전 계획이므로 영향은 아직 확정되지 않았지만, 경쟁자가 없다는 "
                "가정에는 반박 신호입니다."
            ),
        )


@pytest.mark.asyncio
async def test_assumption_finding_prevents_competitor_signal_from_being_neutralized() -> None:
    thesis = StructuredThesis(
        raw_input="핀테크 시장이 성장하고 경쟁자가 없어 실적이 빠르게 성장한다는 논리입니다.",
        main_thesis="핀테크 시장에서 Robinhood의 고성장",
        key_assumptions=["실적 성장", "시장 성장", "경쟁자 없음"],
    )
    document = SourceDocument(
        document_id="competitor-news",
        source_type=EvidenceSourceType.NEWS,
        source_url="https://example.com/competitor-news",
        title="Robinhood 주가 하락",
        content=(
            "Robinhood 주가는 6.13% 하락했습니다. Meta Platforms가 Robinhood와 경쟁할 "
            "수 있는 예측시장 앱을 개발하고 있다는 보도가 나왔습니다."
        ),
    )

    result = await _CompetitorSignalModel().classify_evidence(thesis, document)

    assert result.classification == EvidenceClassification.CONTRADICT
    assert result.impact == EvidenceImpact.MEDIUM
    assert result.relevance_score == 0.9
    assert result.related_assumptions == ["경쟁자 없음"]
    assert "Meta" in result.reason


class _EnglishSummaryModel(LangChainAnalysisModel):
    def __init__(self) -> None:
        pass

    async def _invoke(self, schema, task):  # type: ignore[no-untyped-def]
        del schema, task
        return EvidenceModelOutput(
            classification=EvidenceClassification.SUPPORT,
            impact=EvidenceImpact.MEDIUM,
            relevance_score=0.9,
            reason="Relevant operating evidence",
            related_assumptions=[],
            source_passage_indices=[0],
            content_snippet="English-only summary",
        )


@pytest.mark.asyncio
async def test_non_korean_summary_does_not_discard_valid_classification() -> None:
    thesis = StructuredThesis(
        raw_input="현금 흐름이 성장할 것이라는 투자 논리입니다.",
        main_thesis="장기 현금 흐름 성장",
        key_assumptions=["서비스 매출 성장"],
    )
    document = SourceDocument(
        document_id="news-english-summary",
        source_type=EvidenceSourceType.NEWS,
        source_url="https://news.example/english-summary",
        title="Apple outlook",
        content="Apple reported stronger service revenue growth.",
    )

    result = await _EnglishSummaryModel().classify_evidence(thesis, document)

    assert result.classification == EvidenceClassification.SUPPORT
    assert result.impact == EvidenceImpact.MEDIUM
    assert result.content_snippet == "한글 근거 요약을 생성하지 못했습니다."


class _FailingClassifier:
    async def classify_evidence(self, thesis, document):  # type: ignore[no-untyped-def]
        del thesis, document
        raise RuntimeError("temporary model failure")


@pytest.mark.asyncio
async def test_evidence_node_error_fallback_sanitizes_source_content() -> None:
    thesis = StructuredThesis(
        raw_input="애플의 현금 흐름이 장기적으로 성장할 것이라는 투자 논리입니다.",
        main_thesis="애플의 장기 현금 흐름 성장",
        key_assumptions=["서비스 매출 성장"],
    )
    document = SourceDocument(
        document_id="news-2",
        source_type=EvidenceSourceType.NEWS,
        source_url="https://news.example/article",
        title="Apple 전망",
        content='<a href="https://news.example/article">애플의 현금 흐름 전망</a>&nbsp;',
    )
    dependencies = AgentDependencies(
        context_provider=None,  # type: ignore[arg-type]
        research_tools=None,  # type: ignore[arg-type]
        model=_FailingClassifier(),  # type: ignore[arg-type]
        config=WorkflowConfig(model_max_attempts=1),
    )
    runtime = SimpleNamespace(context=dependencies)

    result = await classify_evidence(
        {
            "research_data": {"filings": [], "news": [document], "macro": []},
            "thesis_snapshot": thesis,
        },
        runtime,  # type: ignore[arg-type]
    )

    evidence = result["evidence_list"][0]
    assert evidence.classification == EvidenceClassification.UNCERTAIN
    assert evidence.impact == EvidenceImpact.LOW
    assert evidence.content_snippet == "분류 모델 오류로 근거 요약을 생성하지 못했습니다."
    assert "<a" not in evidence.content_snippet
