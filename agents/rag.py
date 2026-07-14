"""Provider-neutral hybrid RAG with BM25, dense retrieval, RRF and MMR."""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
from collections import Counter, OrderedDict, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from agents.contracts import EmbeddingModel
from agents.models import EvidenceSourceType, SourceDocument, StructuredThesis
from agents.sanitization import sanitize_source_text

_TOKEN = re.compile(r"[0-9A-Za-z가-힣]{2,}")
_LOW_INFORMATION_PAGE = re.compile(
    r"\b(?:index|archive|topic) page\b|"
    r"\blists? (?:links|frequently searched phrases)\b|"
    r"\bpage (?:lists|links to)\b|"
    r"\bcontains? no (?:company results|reported metrics|new financial figures)\b|"
    r"(?:목록|색인)\s*(?:페이지|문서)",
    re.IGNORECASE,
)
_SOURCE_KEY = {
    EvidenceSourceType.SEC_FILING: "filings",
    EvidenceSourceType.IR: "filings",
    EvidenceSourceType.EARNINGS: "filings",
    EvidenceSourceType.NEWS: "news",
    EvidenceSourceType.MACRO: "macro",
}


@dataclass(frozen=True, slots=True)
class _ChunkDraft:
    document: SourceDocument
    index: int
    text: str

    @property
    def key(self) -> str:
        return f"{self.document.document_id}:{self.index}"

    @property
    def search_text(self) -> str:
        return f"{self.document.title}\n{self.text}"


@dataclass(frozen=True, slots=True)
class _RankedChunk:
    draft: _ChunkDraft
    embedding: tuple[float, ...]
    dense_score: float
    lexical_score: float
    fused_score: float
    quality_score: float


def _tokens(value: str) -> list[str]:
    return [token.casefold() for token in _TOKEN.findall(sanitize_source_text(value))]


def _chunk_text(value: str, *, chunk_chars: int, overlap_chars: int) -> list[str]:
    text = sanitize_source_text(value)
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_chars)
        if end < len(text):
            search_floor = start + int(chunk_chars * 0.6)
            boundaries = [
                text.rfind(marker, search_floor, end) for marker in (". ", "? ", "! ", "。")
            ]
            boundary = max(boundaries)
            if boundary >= search_floor:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        next_start = max(start + 1, end - overlap_chars)
        start = next_start
    return chunks


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Embedding dimensions must match and be non-empty")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _bm25_scores(query: str, corpus: Sequence[list[str]]) -> list[float]:
    if not corpus:
        return []
    query_tokens = set(_tokens(query))
    if not query_tokens:
        return [0.0] * len(corpus)
    document_frequency = Counter(
        token for tokens in corpus for token in set(tokens) if token in query_tokens
    )
    average_length = sum(len(tokens) for tokens in corpus) / max(1, len(corpus))
    k1 = 1.2
    b = 0.75
    scores: list[float] = []
    for tokens in corpus:
        frequencies = Counter(tokens)
        score = 0.0
        for token in query_tokens:
            frequency = frequencies[token]
            if not frequency:
                continue
            frequency_in_documents = document_frequency[token]
            inverse_document_frequency = math.log(
                1 + (len(corpus) - frequency_in_documents + 0.5) / (frequency_in_documents + 0.5)
            )
            length_normalizer = frequency + k1 * (
                1 - b + b * len(tokens) / max(1.0, average_length)
            )
            score += inverse_document_frequency * frequency * (k1 + 1) / length_normalizer
        scores.append(score)
    return scores


class HybridRAGRetriever:
    """Multi-query hybrid retrieval with a bounded content-hash embedding cache."""

    def __init__(
        self,
        embeddings: EmbeddingModel,
        *,
        chunk_chars: int = 1400,
        overlap_chars: int = 200,
        query_limit: int = 6,
        rrf_k: int = 60,
        rerank_pool: int = 30,
        dense_candidate_ratio: float = 0.2,
        min_fused_score_ratio: float = 0.65,
        mmr_lambda: float = 0.75,
        max_chunks_per_document: int = 2,
        max_document_chars: int = 6000,
        max_cache_entries: int = 5000,
    ) -> None:
        if not 0 <= mmr_lambda <= 1:
            raise ValueError("mmr_lambda must be between 0 and 1")
        if overlap_chars >= chunk_chars:
            raise ValueError("overlap_chars must be smaller than chunk_chars")
        if not 0 <= dense_candidate_ratio <= 1:
            raise ValueError("dense_candidate_ratio must be between 0 and 1")
        if not 0 <= min_fused_score_ratio <= 1:
            raise ValueError("min_fused_score_ratio must be between 0 and 1")
        self._embeddings = embeddings
        self._chunk_chars = chunk_chars
        self._overlap_chars = overlap_chars
        self._query_limit = query_limit
        self._rrf_k = rrf_k
        self._rerank_pool = rerank_pool
        self._dense_candidate_ratio = dense_candidate_ratio
        self._min_fused_score_ratio = min_fused_score_ratio
        self._mmr_lambda = mmr_lambda
        self._max_chunks_per_document = max_chunks_per_document
        self._max_document_chars = max_document_chars
        self._max_cache_entries = max_cache_entries
        self._embedding_cache: OrderedDict[str, tuple[float, ...]] = OrderedDict()

    def _queries(
        self,
        ticker: str,
        thesis: StructuredThesis,
        focus_points: Sequence[str],
    ) -> list[str]:
        claims = list(
            dict.fromkeys(
                [
                    *focus_points,
                    *thesis.key_assumptions,
                    thesis.main_thesis,
                    *thesis.positive_signals,
                    *thesis.negative_signals,
                    *thesis.key_risks,
                ]
            )
        )[: self._query_limit]
        return [f"{ticker} 투자 가정 검증: {claim}" for claim in claims]

    def _drafts(self, documents: Sequence[SourceDocument]) -> list[_ChunkDraft]:
        return [
            _ChunkDraft(document=document, index=index, text=text)
            for document in documents
            for index, text in enumerate(
                _chunk_text(
                    document.content,
                    chunk_chars=self._chunk_chars,
                    overlap_chars=self._overlap_chars,
                )
            )
        ]

    async def _document_embeddings(self, drafts: Sequence[_ChunkDraft]) -> list[tuple[float, ...]]:
        hashes = [hashlib.sha256(draft.search_text.encode("utf-8")).hexdigest() for draft in drafts]
        missing: OrderedDict[str, str] = OrderedDict()
        for content_hash, draft in zip(hashes, drafts, strict=True):
            if content_hash in self._embedding_cache:
                self._embedding_cache.move_to_end(content_hash)
            else:
                missing.setdefault(content_hash, draft.search_text)
        if missing:
            vectors = await self._embeddings.aembed_documents(list(missing.values()))
            if len(vectors) != len(missing):
                raise ValueError("Embedding provider returned an unexpected document count")
            for content_hash, vector in zip(missing, vectors, strict=True):
                if not vector:
                    raise ValueError("Embedding provider returned an empty vector")
                self._embedding_cache[content_hash] = tuple(vector)
            while len(self._embedding_cache) > self._max_cache_entries:
                self._embedding_cache.popitem(last=False)
        return [self._embedding_cache[content_hash] for content_hash in hashes]

    async def _rank(
        self,
        drafts: Sequence[_ChunkDraft],
        queries: Sequence[str],
    ) -> list[_RankedChunk]:
        document_embeddings, query_embeddings = await asyncio.gather(
            self._document_embeddings(drafts),
            asyncio.gather(*(self._embeddings.aembed_query(query) for query in queries)),
        )
        corpus_tokens = [_tokens(draft.search_text) for draft in drafts]
        dense_by_query = [
            [_cosine(vector, query_vector) for vector in document_embeddings]
            for query_vector in query_embeddings
        ]
        lexical_by_query = [_bm25_scores(query, corpus_tokens) for query in queries]
        reciprocal_rank_scores = [0.0] * len(drafts)
        for scores_by_query in dense_by_query:
            maximum_score = max(scores_by_query, default=0.0)
            ranked = sorted(range(len(drafts)), key=scores_by_query.__getitem__, reverse=True)
            for rank, index in enumerate(ranked[: self._rerank_pool], start=1):
                if (
                    scores_by_query[index] <= 0
                    or scores_by_query[index] < maximum_score * self._dense_candidate_ratio
                ):
                    continue
                reciprocal_rank_scores[index] += 1 / (self._rrf_k + rank)
        for scores_by_query in lexical_by_query:
            ranked = sorted(range(len(drafts)), key=scores_by_query.__getitem__, reverse=True)
            for rank, index in enumerate(ranked[: self._rerank_pool], start=1):
                if scores_by_query[index] <= 0:
                    continue
                reciprocal_rank_scores[index] += 1 / (self._rrf_k + rank)

        ranked_chunks: list[_RankedChunk] = []
        for index, draft in enumerate(drafts):
            dense_score = max(scores[index] for scores in dense_by_query)
            lexical_score = max(scores[index] for scores in lexical_by_query)
            deterministic_score = float(draft.document.metadata.get("selection_score", 0))
            quality_score = 0.0 if _LOW_INFORMATION_PAGE.search(draft.search_text) else 1.0
            fused_score = reciprocal_rank_scores[index]
            if fused_score > 0:
                fused_score += 0.01 * deterministic_score
            fused_score *= quality_score
            ranked_chunks.append(
                _RankedChunk(
                    draft=draft,
                    embedding=document_embeddings[index],
                    dense_score=dense_score,
                    lexical_score=lexical_score,
                    fused_score=fused_score,
                    quality_score=quality_score,
                )
            )
        return sorted(ranked_chunks, key=lambda item: item.fused_score, reverse=True)

    def _mmr_select(
        self,
        ranked: Sequence[_RankedChunk],
        source_limits: dict[str, int],
    ) -> list[_RankedChunk]:
        initial_pool = list(ranked[: self._rerank_pool])
        maximum = max((item.fused_score for item in initial_pool), default=0.0)
        pool = [
            item
            for item in initial_pool
            if item.fused_score > 0 and item.fused_score >= maximum * self._min_fused_score_ratio
        ]
        if not pool:
            return []
        minimum = min(item.fused_score for item in pool)
        spread = maximum - minimum
        target_documents = sum(source_limits.values())
        target_chunks = min(len(pool), target_documents * self._max_chunks_per_document)
        selected: list[_RankedChunk] = []
        chunks_per_document: Counter[str] = Counter()
        selected_documents: set[str] = set()
        documents_per_source: Counter[str] = Counter()

        while pool and len(selected) < target_chunks:
            best: _RankedChunk | None = None
            best_score = float("-inf")
            for candidate in pool:
                document_id = candidate.draft.document.document_id
                source_key = _SOURCE_KEY[candidate.draft.document.source_type]
                if chunks_per_document[document_id] >= self._max_chunks_per_document:
                    continue
                if (
                    document_id not in selected_documents
                    and documents_per_source[source_key] >= source_limits[source_key]
                ):
                    continue
                relevance = (candidate.fused_score - minimum) / spread if spread else 1.0
                redundancy = max(
                    (_cosine(candidate.embedding, item.embedding) for item in selected),
                    default=0.0,
                )
                score = self._mmr_lambda * relevance - (1 - self._mmr_lambda) * redundancy
                if score > best_score:
                    best = candidate
                    best_score = score
            if best is None:
                break
            pool.remove(best)
            selected.append(best)
            document_id = best.draft.document.document_id
            chunks_per_document[document_id] += 1
            if document_id not in selected_documents:
                selected_documents.add(document_id)
                documents_per_source[_SOURCE_KEY[best.draft.document.source_type]] += 1
        return selected

    def _assemble_documents(
        self,
        selected: Sequence[_RankedChunk],
        drafts: Sequence[_ChunkDraft],
    ) -> list[SourceDocument]:
        chunks_by_document: dict[str, dict[int, _ChunkDraft]] = defaultdict(dict)
        for draft in drafts:
            chunks_by_document[draft.document.document_id][draft.index] = draft
        selected_by_document: dict[str, list[_RankedChunk]] = defaultdict(list)
        for item in selected:
            selected_by_document[item.draft.document.document_id].append(item)

        documents: list[SourceDocument] = []
        ordered_groups = sorted(
            selected_by_document.values(),
            key=lambda group: max(item.fused_score for item in group),
            reverse=True,
        )
        for group in ordered_groups:
            document = group[0].draft.document
            available = chunks_by_document[document.document_id]
            selected_indices = sorted({item.draft.index for item in group})
            expanded_indices = sorted(
                {
                    neighbor
                    for index in selected_indices
                    for neighbor in (index - 1, index, index + 1)
                    if neighbor in available
                }
            )
            content = "\n".join(available[index].text for index in expanded_indices)
            metadata = {
                **document.metadata,
                "rag_enabled": True,
                "rag_score": round(max(item.fused_score for item in group), 6),
                "rag_dense_score": round(max(item.dense_score for item in group), 6),
                "rag_lexical_score": round(max(item.lexical_score for item in group), 6),
                "rag_quality_score": min(item.quality_score for item in group),
                "rag_chunk_indices": selected_indices,
                "rag_expanded_chunk_indices": expanded_indices,
            }
            documents.append(
                document.model_copy(
                    update={
                        "content": content[: self._max_document_chars].rstrip(),
                        "metadata": metadata,
                    }
                )
            )
        return documents

    async def select_documents(
        self,
        *,
        ticker: str,
        thesis: StructuredThesis,
        focus_points: Sequence[str],
        documents: Sequence[SourceDocument],
        source_limits: dict[str, int],
    ) -> list[SourceDocument]:
        if not documents or not sum(source_limits.values()):
            return []
        queries = self._queries(ticker, thesis, focus_points)
        drafts = self._drafts(documents)
        if not drafts or not queries:
            return []
        ranked = await self._rank(drafts, queries)
        selected = self._mmr_select(ranked, source_limits)
        return self._assemble_documents(selected, drafts)
