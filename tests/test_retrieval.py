from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from agents.evidence_policy import is_meaningful_directional_evidence
from agents.models import (
    EvidenceAssessment,
    EvidenceClassification,
    EvidenceImpact,
    EvidenceItem,
    EvidenceSourceType,
    SourceDocument,
    StructuredThesis,
)
from agents.nodes.evidence import classify_evidence
from agents.retrieval import extract_relevant_passages, preselect_documents
from agents.runtime import AgentDependencies, WorkflowConfig


def _thesis() -> StructuredThesis:
    return StructuredThesis(
        raw_input="NVDA benefits from continued AI infrastructure spending growth.",
        main_thesis="AI infrastructure spending drives data center growth",
        key_assumptions=["hyperscaler AI CAPEX keeps growing"],
        key_risks=["customers reduce AI infrastructure budgets"],
    )


def test_default_relevance_threshold_is_055() -> None:
    assert WorkflowConfig().min_relevance_score == 0.55


def _document(
    document_id: str,
    title: str,
    *,
    source_type: EvidenceSourceType = EvidenceSourceType.NEWS,
    published_at: datetime | None = None,
    source: str = "Reuters",
) -> SourceDocument:
    return SourceDocument(
        document_id=document_id,
        source_type=source_type,
        source_url=f"https://example.com/{document_id}",
        title=title,
        content=f"{title}. NVDA AI infrastructure spending and data center demand.",
        published_at=published_at,
        metadata={"source": source},
    )


def test_preselection_removes_stale_duplicate_and_irrelevant_macro_documents() -> None:
    now = datetime(2026, 7, 14, tzinfo=UTC)
    fresh = now - timedelta(days=2)
    research_data = {
        "filings": [],
        "news": [
            _document("news-1", "NVDA AI CAPEX outlook improves - Reuters", published_at=fresh),
            _document(
                "news-2",
                "NVDA AI CAPEX outlook improves - AP",
                published_at=now - timedelta(days=1),
                source="AP",
            ),
            _document(
                "news-stale", "NVDA old report - Reuters", published_at=now - timedelta(days=60)
            ),
            _document("news-3", "NVDA data center demand rises - Reuters", published_at=fresh),
        ],
        "macro": [
            _document(
                "cpi",
                "FRED CPI",
                source_type=EvidenceSourceType.MACRO,
                published_at=None,
            )
        ],
    }

    selected = preselect_documents(
        research_data,
        ticker="NVDA",
        thesis=_thesis(),
        focus_points=_thesis().key_assumptions,
        lookback_days=30,
        min_news_score=0.30,
        source_limits={"filings": 3, "news": 2, "macro": 2},
        now=now,
    )

    selected_ids = {item.document_id for item in selected}
    assert "news-stale" not in selected_ids
    assert "cpi" not in selected_ids
    assert len(selected) == 2
    assert "news-1" not in selected_ids
    assert "news-2" in selected_ids
    assert all("selection_score" in item.metadata for item in selected)


def test_preselection_rejects_news_about_a_different_hood() -> None:
    now = datetime(2026, 7, 14, tzinfo=UTC)
    company_name = "Robinhood Markets, Inc."
    unrelated = SourceDocument(
        document_id="hoodie",
        source_type=EvidenceSourceType.NEWS,
        source_url="https://example.com/hoodie",
        title="Best hood and sweatshirt styles this summer",
        content="A guide to hooded sweatshirts and casual clothing.",
        published_at=now,
        metadata={"company_name": company_name},
    )
    relevant = SourceDocument(
        document_id="robinhood-results",
        source_type=EvidenceSourceType.NEWS,
        source_url="https://example.com/robinhood-results",
        title="Robinhood reports stronger trading revenue",
        content="Robinhood revenue increased as customer activity improved.",
        published_at=now,
        metadata={"company_name": company_name},
    )

    selected = preselect_documents(
        {"filings": [], "news": [unrelated, relevant], "macro": []},
        ticker="HOOD",
        thesis=_thesis(),
        focus_points=[],
        lookback_days=30,
        min_news_score=0.30,
        source_limits={"filings": 0, "news": 5, "macro": 0},
        now=now,
    )

    assert [item.document_id for item in selected] == ["robinhood-results"]


def test_extract_relevant_passages_keeps_matching_section_within_budget() -> None:
    content = "\n".join(
        [
            "Corporate cover page and administrative information. " * 20,
            "AI infrastructure spending increased while data center demand remained strong. " * 8,
            "Unrelated legal boilerplate and signature information. " * 20,
        ]
    )

    selected = extract_relevant_passages(
        content,
        ["AI infrastructure spending", "data center demand"],
        max_chars=700,
    )

    assert "AI infrastructure spending" in selected
    assert len(selected) <= 700


class _LowRelevanceModel:
    async def classify_evidence(  # type: ignore[no-untyped-def]
        self, thesis, document, evidence_history_summary=""
    ):
        del evidence_history_summary
        return EvidenceAssessment(
            classification=EvidenceClassification.SUPPORT,
            impact=EvidenceImpact.HIGH,
            relevance_score=0.2,
            reason="General market commentary",
            related_assumptions=[thesis.key_assumptions[0]],
            source_excerpt=document.content,
            content_snippet="일반적인 반도체 시장 전망에 관한 논평입니다.",
        )


@pytest.mark.asyncio
async def test_low_relevance_directional_result_is_neutralized_before_debate() -> None:
    document = _document(
        "market-commentary",
        "General semiconductor market commentary",
        published_at=datetime(2026, 7, 14, tzinfo=UTC),
    )
    dependencies = AgentDependencies(
        context_provider=None,  # type: ignore[arg-type]
        research_tools=None,  # type: ignore[arg-type]
        model=_LowRelevanceModel(),  # type: ignore[arg-type]
        config=WorkflowConfig(min_relevance_score=0.65),
    )

    result = await classify_evidence(
        {
            "research_data": {"filings": [], "news": [document], "macro": []},
            "thesis_snapshot": _thesis(),
        },
        SimpleNamespace(context=dependencies),  # type: ignore[arg-type]
    )

    evidence = result["evidence_list"][0]
    assert evidence.classification == EvidenceClassification.NEUTRAL
    assert evidence.impact == EvidenceImpact.LOW
    assert result["needs_more_research"] is True


@pytest.mark.asyncio
async def test_historical_document_is_neutralized_without_model_reclassification() -> None:
    document = _document(
        "already-scored-document",
        "The same fact collected in an earlier analysis.",
        published_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    model = _LowRelevanceModel()
    dependencies = AgentDependencies(
        context_provider=None,  # type: ignore[arg-type]
        research_tools=None,  # type: ignore[arg-type]
        model=model,  # type: ignore[arg-type]
        config=WorkflowConfig(),
    )

    result = await classify_evidence(
        {
            "research_data": {"filings": [], "news": [document], "macro": []},
            "thesis_snapshot": _thesis(),
            "evidence_history_document_ids": [document.document_id],
            "evidence_history_summary": "과거 동일 문서가 이미 반영됐습니다.",
        },
        SimpleNamespace(context=dependencies),  # type: ignore[arg-type]
    )

    evidence = result["evidence_list"][0]
    assert evidence.classification == EvidenceClassification.NEUTRAL
    assert evidence.impact == EvidenceImpact.LOW
    assert "중복 제외" in evidence.content_snippet


def test_low_impact_directional_evidence_is_not_meaningful() -> None:
    item = EvidenceItem(
        document_id="weak-support",
        source_type=EvidenceSourceType.NEWS,
        source_url="https://example.com/weak-support",
        content_snippet="Minor commentary",
        classification=EvidenceClassification.SUPPORT,
        impact=EvidenceImpact.LOW,
        reason="Low materiality",
    )

    assert is_meaningful_directional_evidence(item) is False
