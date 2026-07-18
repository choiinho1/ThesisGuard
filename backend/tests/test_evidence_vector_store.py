from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from qdrant_client import QdrantClient

from thesisguard_backend.evidence_vector_store import (
    EvidenceVectorDocument,
    EvidenceVectorStore,
)


class KeywordEmbeddings:
    @staticmethod
    def _vector(text: str) -> list[float]:
        normalized = text.casefold()
        return [
            1.0 if "demand" in normalized else 0.0,
            1.0 if "margin" in normalized else 0.0,
            1.0 if "regulation" in normalized else 0.0,
        ]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    async def aembed_query(self, text: str) -> list[float]:
        return self._vector(text)


def _document(
    *,
    portfolio_id: uuid.UUID,
    thesis_id: uuid.UUID,
    content: str,
) -> EvidenceVectorDocument:
    evidence_id = uuid.uuid4()
    return EvidenceVectorDocument(
        evidence_id=evidence_id,
        portfolio_id=portfolio_id,
        holding_id=uuid.uuid4(),
        thesis_id=thesis_id,
        ticker="NVDA",
        main_thesis="AI infrastructure growth",
        document_id=f"doc-{evidence_id}",
        content_snippet=content,
        reason="Relevant assessment",
        related_assumptions=[content],
        source_type="NEWS",
        classification="SUPPORT",
        impact="HIGH",
        published_at=datetime(2026, 7, 16, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_semantic_search_filters_results_to_the_requested_portfolio() -> None:
    portfolio_id = uuid.uuid4()
    other_portfolio_id = uuid.uuid4()
    margin = _document(
        portfolio_id=portfolio_id,
        thesis_id=uuid.uuid4(),
        content="margin compression risk",
    )
    demand = _document(
        portfolio_id=portfolio_id,
        thesis_id=uuid.uuid4(),
        content="accelerating demand growth",
    )
    other_margin = _document(
        portfolio_id=other_portfolio_id,
        thesis_id=uuid.uuid4(),
        content="margin compression risk",
    )
    store = EvidenceVectorStore(
        embeddings=KeywordEmbeddings(),
        client=QdrantClient(location=":memory:"),
        collection_name="evidence",
    )

    assert await store.index_documents([margin, demand, other_margin]) == 3
    matches = await store.search("margin pressure", portfolio_id=portfolio_id, limit=1)

    assert [match.evidence_id for match in matches] == [margin.evidence_id]
    await store.close()


@pytest.mark.asyncio
async def test_local_qdrant_store_persists_vectors_and_skips_existing_points(tmp_path) -> None:
    portfolio_id = uuid.uuid4()
    thesis_id = uuid.uuid4()
    document = _document(
        portfolio_id=portfolio_id,
        thesis_id=thesis_id,
        content="accelerating demand growth",
    )
    path = tmp_path / "qdrant"
    first = EvidenceVectorStore(
        embeddings=KeywordEmbeddings(),
        client=QdrantClient(path=str(path)),
        collection_name="evidence",
    )
    assert await first.index_documents([document], skip_existing=True) == 1
    assert await first.index_documents([document], skip_existing=True) == 0
    await first.close()

    reopened = EvidenceVectorStore(
        embeddings=KeywordEmbeddings(),
        client=QdrantClient(path=str(path)),
        collection_name="evidence",
    )
    matches = await reopened.search("demand outlook", portfolio_id=portfolio_id)
    assert [match.evidence_id for match in matches] == [document.evidence_id]

    await reopened.delete_thesis(thesis_id)
    assert await reopened.search("demand outlook", portfolio_id=portfolio_id) == []
    await reopened.close()
