"""Persistent Qdrant index for portfolio-scoped semantic Evidence retrieval."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from agents.contracts import EmbeddingModel
from qdrant_client import QdrantClient
from qdrant_client import models as qmodels
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from thesisguard_backend import models as orm
from thesisguard_backend.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EvidenceVectorDocument:
    evidence_id: uuid.UUID
    portfolio_id: uuid.UUID
    holding_id: uuid.UUID
    thesis_id: uuid.UUID
    ticker: str
    main_thesis: str
    document_id: str
    content_snippet: str
    reason: str
    related_assumptions: list[str]
    source_type: str
    classification: str
    impact: str
    published_at: datetime | None

    @property
    def embedding_text(self) -> str:
        assumptions = " / ".join(self.related_assumptions)
        return "\n".join(
            part
            for part in (
                f"Ticker: {self.ticker}",
                f"Investment thesis: {self.main_thesis}",
                f"Related assumptions: {assumptions}" if assumptions else "",
                f"Evidence: {self.content_snippet}",
                f"Assessment reason: {self.reason}" if self.reason else "",
                f"Classification: {self.classification}; impact: {self.impact}",
            )
            if part
        )

    @property
    def payload(self) -> dict[str, str | list[str] | None]:
        return {
            "evidence_id": str(self.evidence_id),
            "portfolio_id": str(self.portfolio_id),
            "holding_id": str(self.holding_id),
            "thesis_id": str(self.thesis_id),
            "ticker": self.ticker,
            "document_id": self.document_id,
            "related_assumptions": self.related_assumptions,
            "source_type": self.source_type,
            "classification": self.classification,
            "impact": self.impact,
            "published_at": self.published_at.isoformat() if self.published_at else None,
        }


@dataclass(frozen=True, slots=True)
class SemanticEvidenceMatch:
    evidence_id: uuid.UUID
    score: float


class EvidenceVectorStore:
    """Embed Evidence once, persist it in Qdrant, and search within a portfolio."""

    def __init__(
        self,
        *,
        embeddings: EmbeddingModel,
        client: QdrantClient,
        collection_name: str,
        default_limit: int = 20,
        score_threshold: float | None = None,
    ) -> None:
        self._embeddings = embeddings
        self._client = client
        self._collection_name = collection_name
        self._default_limit = max(1, default_limit)
        self._score_threshold = score_threshold
        self._client_lock = asyncio.Lock()

    async def _collection_exists(self) -> bool:
        async with self._client_lock:
            return await asyncio.to_thread(
                self._client.collection_exists,
                self._collection_name,
            )

    async def _ensure_collection(self, vector_size: int) -> None:
        async with self._client_lock:
            exists = await asyncio.to_thread(
                self._client.collection_exists,
                self._collection_name,
            )
            if exists:
                collection = await asyncio.to_thread(
                    self._client.get_collection,
                    self._collection_name,
                )
                configured = collection.config.params.vectors
                configured_size = getattr(configured, "size", None)
                if configured_size is not None and configured_size != vector_size:
                    raise ValueError(
                        "Qdrant collection vector size does not match the configured "
                        f"embedding model: collection={configured_size}, model={vector_size}. "
                        "Use a new QDRANT_EVIDENCE_COLLECTION name and backfill it."
                    )
                return
            await asyncio.to_thread(
                self._client.create_collection,
                collection_name=self._collection_name,
                vectors_config=qmodels.VectorParams(
                    size=vector_size,
                    distance=qmodels.Distance.COSINE,
                ),
            )

    async def index_documents(
        self,
        documents: list[EvidenceVectorDocument],
        *,
        skip_existing: bool = False,
    ) -> int:
        if not documents:
            return 0

        pending = documents
        if skip_existing and await self._collection_exists():
            ids = [document.evidence_id for document in documents]
            async with self._client_lock:
                records = await asyncio.to_thread(
                    self._client.retrieve,
                    collection_name=self._collection_name,
                    ids=ids,
                    with_payload=False,
                    with_vectors=False,
                )
            existing_ids = {str(record.id) for record in records}
            pending = [
                document for document in documents if str(document.evidence_id) not in existing_ids
            ]
        if not pending:
            return 0

        vectors = await self._embeddings.aembed_documents(
            [document.embedding_text for document in pending]
        )
        if len(vectors) != len(pending) or any(not vector for vector in vectors):
            raise ValueError("Embedding provider returned incomplete Evidence vectors")
        await self._ensure_collection(len(vectors[0]))
        points = [
            qmodels.PointStruct(
                id=document.evidence_id,
                vector=vector,
                payload=document.payload,
            )
            for document, vector in zip(pending, vectors, strict=True)
        ]
        async with self._client_lock:
            await asyncio.to_thread(
                self._client.upsert,
                collection_name=self._collection_name,
                points=points,
                wait=True,
            )
        return len(points)

    async def search(
        self,
        question: str,
        *,
        portfolio_id: uuid.UUID,
        limit: int | None = None,
    ) -> list[SemanticEvidenceMatch]:
        if not await self._collection_exists():
            return []
        vector = await self._embeddings.aembed_query(question)
        if not vector:
            raise ValueError("Embedding provider returned an empty query vector")
        query_filter = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="portfolio_id",
                    match=qmodels.MatchValue(value=str(portfolio_id)),
                )
            ]
        )
        async with self._client_lock:
            response = await asyncio.to_thread(
                self._client.query_points,
                collection_name=self._collection_name,
                query=vector,
                query_filter=query_filter,
                limit=limit or self._default_limit,
                with_payload=["evidence_id"],
                with_vectors=False,
                score_threshold=self._score_threshold,
            )
        matches: list[SemanticEvidenceMatch] = []
        for point in response.points:
            payload = point.payload or {}
            raw_evidence_id = payload.get("evidence_id")
            try:
                evidence_id = uuid.UUID(str(raw_evidence_id or point.id))
            except ValueError:
                continue
            matches.append(SemanticEvidenceMatch(evidence_id=evidence_id, score=point.score))
        return matches

    async def delete_thesis(self, thesis_id: uuid.UUID) -> None:
        if not await self._collection_exists():
            return
        selector = qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="thesis_id",
                        match=qmodels.MatchValue(value=str(thesis_id)),
                    )
                ]
            )
        )
        async with self._client_lock:
            await asyncio.to_thread(
                self._client.delete,
                collection_name=self._collection_name,
                points_selector=selector,
                wait=True,
            )

    async def close(self) -> None:
        async with self._client_lock:
            await asyncio.to_thread(self._client.close)


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def evidence_vector_document(
    *,
    evidence: orm.Evidence,
    thesis: orm.Thesis,
    holding: orm.Holding,
) -> EvidenceVectorDocument:
    return EvidenceVectorDocument(
        evidence_id=evidence.id,
        portfolio_id=holding.portfolio_id,
        holding_id=holding.id,
        thesis_id=thesis.id,
        ticker=holding.ticker,
        main_thesis=thesis.main_thesis,
        document_id=evidence.document_id,
        content_snippet=evidence.content_snippet,
        reason=evidence.reason,
        related_assumptions=list(evidence.related_assumptions),
        source_type=_enum_value(evidence.source_type),
        classification=_enum_value(evidence.classification),
        impact=_enum_value(evidence.impact),
        published_at=evidence.published_at,
    )


_UNINITIALIZED = object()
_store: EvidenceVectorStore | None | object = _UNINITIALIZED


def get_evidence_vector_store() -> EvidenceVectorStore | None:
    global _store
    if _store is not _UNINITIALIZED:
        return _store if isinstance(_store, EvidenceVectorStore) else None

    from thesisguard_backend.agent_adapters import create_embedding_model

    settings = get_settings()
    embeddings = create_embedding_model()
    if embeddings is None:
        _store = None
        return None
    if settings.qdrant_url:
        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            timeout=max(5, int(settings.rag_embedding_timeout_seconds)),
        )
    else:
        path = Path(settings.qdrant_path).resolve()
        path.mkdir(parents=True, exist_ok=True)
        client = QdrantClient(path=str(path))
    _store = EvidenceVectorStore(
        embeddings=embeddings,
        client=client,
        collection_name=settings.qdrant_evidence_collection,
        default_limit=settings.portfolio_qa_semantic_limit,
        score_threshold=settings.portfolio_qa_score_threshold,
    )
    return _store


async def index_analysis_evidence(
    *,
    evidence_rows: list[orm.Evidence],
    thesis: orm.Thesis,
    holding: orm.Holding,
) -> int:
    store = get_evidence_vector_store()
    if store is None:
        return 0
    try:
        return await store.index_documents(
            [
                evidence_vector_document(evidence=row, thesis=thesis, holding=holding)
                for row in evidence_rows
            ]
        )
    except Exception:  # noqa: BLE001 - analysis persistence must survive index outages
        logger.exception("Failed to index analysis Evidence in Qdrant")
        return 0


async def search_portfolio_evidence(
    question: str,
    *,
    portfolio_id: uuid.UUID,
    limit: int | None = None,
) -> list[SemanticEvidenceMatch] | None:
    store = get_evidence_vector_store()
    if store is None:
        return None
    try:
        return await store.search(question, portfolio_id=portfolio_id, limit=limit)
    except Exception:  # noqa: BLE001 - caller applies an explicit recency fallback
        logger.exception("Portfolio Evidence semantic search failed")
        return None


async def delete_thesis_evidence_vectors(thesis_id: uuid.UUID) -> None:
    store = get_evidence_vector_store()
    if store is None:
        return
    try:
        await store.delete_thesis(thesis_id)
    except Exception:  # noqa: BLE001 - stale points are filtered against DB rows at query time
        logger.exception("Failed to delete superseded thesis Evidence vectors")


async def backfill_evidence_vector_store(session_factory: async_sessionmaker) -> int:
    store = get_evidence_vector_store()
    if store is None:
        return 0
    indexed = 0
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(orm.Evidence, orm.Thesis, orm.Holding)
                .join(orm.Thesis, orm.Thesis.id == orm.Evidence.thesis_id)
                .join(orm.Holding, orm.Holding.id == orm.Thesis.holding_id)
                .order_by(orm.Evidence.created_at.asc())
            )
        ).all()
        for start in range(0, len(rows), 64):
            batch = rows[start : start + 64]
            try:
                indexed += await store.index_documents(
                    [
                        evidence_vector_document(
                            evidence=evidence,
                            thesis=thesis,
                            holding=holding,
                        )
                        for evidence, thesis, holding in batch
                    ],
                    skip_existing=True,
                )
            except Exception:  # noqa: BLE001 - startup remains available without Vector Store
                logger.exception("Evidence Vector Store backfill failed")
                break
    return indexed


async def close_evidence_vector_store() -> None:
    global _store
    if isinstance(_store, EvidenceVectorStore):
        await _store.close()
    _store = _UNINITIALIZED
