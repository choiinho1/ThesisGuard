"""RAGAS-backed, provider-neutral retrieval benchmark utilities."""

from __future__ import annotations

import json
import math
import time
import warnings
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from agents.contracts import DocumentRetriever
from agents.models import SourceDocument, StructuredThesis


class RetrievalBenchmarkCase(BaseModel):
    case_id: str
    ticker: str
    thesis: StructuredThesis
    focus_points: list[str] = Field(default_factory=list)
    documents: list[SourceDocument]
    source_limits: dict[str, int]
    reference_document_ids: list[str] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class RetrievalCaseResult:
    case_id: str
    retrieved_document_ids: list[str]
    reference_document_ids: list[str]
    context_precision: float
    context_recall: float
    reciprocal_rank: float
    ndcg: float
    latency_ms: float


@dataclass(frozen=True, slots=True)
class RetrievalBenchmarkReport:
    cases: list[RetrievalCaseResult]
    context_precision: float
    context_recall: float
    mean_reciprocal_rank: float
    ndcg: float
    hit_rate: float
    mean_latency_ms: float

    def to_dict(self) -> dict:
        return {
            "summary": {
                "cases": len(self.cases),
                "context_precision": round(self.context_precision, 4),
                "context_recall": round(self.context_recall, 4),
                "mean_reciprocal_rank": round(self.mean_reciprocal_rank, 4),
                "ndcg": round(self.ndcg, 4),
                "hit_rate": round(self.hit_rate, 4),
                "mean_latency_ms": round(self.mean_latency_ms, 2),
            },
            "cases": [asdict(case) for case in self.cases],
        }


def load_retrieval_benchmark(path: Path) -> list[RetrievalBenchmarkCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [RetrievalBenchmarkCase.model_validate(item) for item in payload]


def _reciprocal_rank(retrieved: Sequence[str], reference: set[str]) -> float:
    for rank, document_id in enumerate(retrieved, start=1):
        if document_id in reference:
            return 1 / rank
    return 0.0


def _ndcg(retrieved: Sequence[str], reference: set[str]) -> float:
    gains = [1.0 if document_id in reference else 0.0 for document_id in retrieved]
    discounted_gain = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(gains, start=1))
    ideal_count = min(len(reference), len(retrieved))
    ideal_gain = sum(1 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    return discounted_gain / ideal_gain if ideal_gain else 0.0


async def _ragas_id_scores(retrieved: list[str], reference: list[str]) -> tuple[float, float]:
    # Ragas 0.4.3 exposes these two metrics on the legacy public module while
    # announcing their future collections-module location.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from ragas import SingleTurnSample
        from ragas.metrics import IDBasedContextPrecision, IDBasedContextRecall

    sample = SingleTurnSample(
        retrieved_context_ids=retrieved,
        reference_context_ids=reference,
    )
    precision = await IDBasedContextPrecision().single_turn_ascore(sample)
    recall = await IDBasedContextRecall().single_turn_ascore(sample)
    return float(precision), float(recall)


async def evaluate_retriever(
    retriever: DocumentRetriever,
    cases: Sequence[RetrievalBenchmarkCase],
) -> RetrievalBenchmarkReport:
    results: list[RetrievalCaseResult] = []
    for case in cases:
        started = time.perf_counter()
        selected = await retriever.select_documents(
            ticker=case.ticker,
            thesis=case.thesis,
            focus_points=case.focus_points,
            documents=case.documents,
            source_limits=case.source_limits,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        retrieved = list(dict.fromkeys(document.document_id for document in selected))
        precision, recall = await _ragas_id_scores(retrieved, case.reference_document_ids)
        reference = set(case.reference_document_ids)
        results.append(
            RetrievalCaseResult(
                case_id=case.case_id,
                retrieved_document_ids=retrieved,
                reference_document_ids=case.reference_document_ids,
                context_precision=precision,
                context_recall=recall,
                reciprocal_rank=_reciprocal_rank(retrieved, reference),
                ndcg=_ndcg(retrieved, reference),
                latency_ms=round(latency_ms, 2),
            )
        )

    count = len(results)
    if not count:
        raise ValueError("Retrieval benchmark requires at least one case")
    mean = lambda values: sum(values) / count  # noqa: E731 - compact metric aggregation
    return RetrievalBenchmarkReport(
        cases=results,
        context_precision=mean([result.context_precision for result in results]),
        context_recall=mean([result.context_recall for result in results]),
        mean_reciprocal_rank=mean([result.reciprocal_rank for result in results]),
        ndcg=mean([result.ndcg for result in results]),
        hit_rate=mean([float(result.reciprocal_rank > 0) for result in results]),
        mean_latency_ms=mean([result.latency_ms for result in results]),
    )
