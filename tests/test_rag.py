from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agents.models import EvidenceSourceType, SourceDocument, StructuredThesis
from agents.rag import HybridRAGRetriever


class _FakeEmbeddings:
    def __init__(self) -> None:
        self.document_calls = 0
        self.query_calls = 0

    @staticmethod
    def _vector(text: str) -> list[float]:
        normalized = text.casefold()
        competition = any(
            term in normalized for term in ("경쟁", "compet", "rival", "meta platforms")
        )
        growth = any(term in normalized for term in ("실적", "매출", "revenue", "earnings"))
        growth = growth or "growth" in normalized
        return [float(competition), float(growth), 0.1]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_calls += 1
        return [self._vector(text) for text in texts]

    async def aembed_query(self, text: str) -> list[float]:
        self.query_calls += 1
        return self._vector(text)


def _document(document_id: str, content: str) -> SourceDocument:
    return SourceDocument(
        document_id=document_id,
        source_type=EvidenceSourceType.NEWS,
        source_url=f"https://example.com/{document_id}",
        title=f"Robinhood {document_id}",
        content=content,
        published_at=datetime(2026, 7, 14, tzinfo=UTC),
        metadata={"selection_score": 0.7, "company_name": "Robinhood Markets, Inc."},
    )


@pytest.mark.asyncio
async def test_hybrid_rag_finds_competitor_signal_and_diversifies() -> None:
    embeddings = _FakeEmbeddings()
    retriever = HybridRAGRetriever(embeddings, chunk_chars=500, overlap_chars=50)
    thesis = StructuredThesis(
        raw_input="Robinhood grows as earnings rise and competition stays limited.",
        main_thesis="Robinhood long-term growth",
        key_assumptions=["revenue and earnings growth", "limited competition"],
    )
    documents = [
        _document("price", "Robinhood shares moved lower during the trading session."),
        _document(
            "competition",
            "Meta Platforms is developing a competing prediction markets app.",
        ),
        _document("growth", "Robinhood revenue and earnings increased year over year."),
    ]

    selected = await retriever.select_documents(
        ticker="HOOD",
        thesis=thesis,
        focus_points=[],
        documents=documents,
        source_limits={"filings": 0, "news": 2, "macro": 0},
    )

    assert {document.document_id for document in selected} == {"competition", "growth"}
    assert all(document.metadata["rag_enabled"] is True for document in selected)
    assert all("rag_dense_score" in document.metadata for document in selected)


@pytest.mark.asyncio
async def test_hybrid_rag_reuses_content_hash_embedding_cache() -> None:
    embeddings = _FakeEmbeddings()
    retriever = HybridRAGRetriever(embeddings, chunk_chars=500, overlap_chars=50)
    thesis = StructuredThesis(
        raw_input="경쟁자가 없어서 장기적으로 성장한다는 투자 논리입니다.",
        main_thesis="Robinhood의 장기 성장",
        key_assumptions=["경쟁자 없음"],
    )
    documents = [_document("competition", "A rival is developing a competing app.")]
    arguments = {
        "ticker": "HOOD",
        "thesis": thesis,
        "focus_points": [],
        "documents": documents,
        "source_limits": {"filings": 0, "news": 1, "macro": 0},
    }

    await retriever.select_documents(**arguments)
    await retriever.select_documents(**arguments)

    assert embeddings.document_calls == 1
    assert embeddings.query_calls == 4


@pytest.mark.asyncio
async def test_hybrid_rag_uses_title_and_abstains_from_low_information_pages() -> None:
    embeddings = _FakeEmbeddings()
    retriever = HybridRAGRetriever(embeddings, chunk_chars=500, overlap_chars=50)
    thesis = StructuredThesis(
        raw_input="Revenue growth is the main assumption for this investment thesis.",
        main_thesis="Long-term revenue growth",
        key_assumptions=["revenue and earnings growth"],
    )
    documents = [
        _document(
            "signal",
            "The segment increased from 9.2 billion dollars to 11.8 billion dollars.",
        ).model_copy(update={"title": "Revenue and earnings growth accelerates"}),
        _document(
            "index",
            "This archive page lists links about revenue, earnings and growth. "
            "It contains no reported metrics or company statements.",
        ),
        _document("price", "Shares moved during the afternoon trading session."),
    ]

    selected = await retriever.select_documents(
        ticker="TEST",
        thesis=thesis,
        focus_points=[],
        documents=documents,
        source_limits={"filings": 0, "news": 2, "macro": 0},
    )

    assert [document.document_id for document in selected] == ["signal"]
    assert selected[0].metadata["rag_quality_score"] == 1
