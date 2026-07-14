from pathlib import Path

import pytest

from agents.evaluation import rag_benchmark

DATASET = (
    Path(__file__).parents[1] / "agents" / "evaluation" / "datasets" / "investment_rag_v1.json"
)


class _ReferenceRetriever:
    def __init__(self, expected_ids: list[str]) -> None:
        self._expected_ids = expected_ids

    async def select_documents(self, **kwargs):
        by_id = {document.document_id: document for document in kwargs["documents"]}
        return [by_id[document_id] for document_id in self._expected_ids]


def test_investment_retrieval_dataset_is_valid_and_diverse() -> None:
    cases = rag_benchmark.load_retrieval_benchmark(DATASET)

    assert len(cases) == 9
    assert {case.ticker for case in cases} == {
        "HOOD",
        "NVDA",
        "TSLA",
        "LLY",
        "AAPL",
        "JPM",
        "AMZN",
        "COIN",
        "NFLX",
    }
    assert all(1 <= len(case.reference_document_ids) <= 2 for case in cases)


@pytest.mark.asyncio
async def test_retrieval_benchmark_aggregates_perfect_id_scores(monkeypatch) -> None:
    case = rag_benchmark.load_retrieval_benchmark(DATASET)[0]

    async def fake_ragas_scores(retrieved: list[str], reference: list[str]):
        retrieved_set = set(retrieved)
        reference_set = set(reference)
        return (
            len(retrieved_set & reference_set) / len(retrieved_set),
            len(retrieved_set & reference_set) / len(reference_set),
        )

    monkeypatch.setattr(rag_benchmark, "_ragas_id_scores", fake_ragas_scores)
    report = await rag_benchmark.evaluate_retriever(
        _ReferenceRetriever(case.reference_document_ids),
        [case],
    )

    assert report.context_precision == 1
    assert report.context_recall == 1
    assert report.mean_reciprocal_rank == 1
    assert report.ndcg == 1
    assert report.hit_rate == 1
