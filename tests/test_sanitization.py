from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.model import LangChainAnalysisModel
from agents.models import (
    EvidenceAssessment,
    EvidenceClassification,
    EvidenceImpact,
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
    assert safe_source_snippet(
        "<script>ignore()</script>", "<b>Apple 실적 전망</b>"
    ) == "Apple 실적 전망"


class _InvalidCitationModel(LangChainAnalysisModel):
    def __init__(self) -> None:
        pass

    async def _invoke(self, schema, task):  # type: ignore[no-untyped-def]
        del schema, task
        return EvidenceAssessment(
            classification=EvidenceClassification.SUPPORT,
            impact=EvidenceImpact.HIGH,
            reason="모델이 만든 검증 불가능한 인용문",
            content_snippet="원문에 없는 문장",
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
    assert result.content_snippet == "애플의 현금 흐름 전망"
    assert "<a" not in result.content_snippet


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
    assert evidence.content_snippet == "애플의 현금 흐름 전망"
    assert "<a" not in evidence.content_snippet
