"""Evaluate live Upstage hybrid retrieval against the investment golden set."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from agents.evaluation.rag_benchmark import evaluate_retriever, load_retrieval_benchmark
from agents.rag import HybridRAGRetriever

from thesisguard_backend.agent_adapters import create_embedding_model
from thesisguard_backend.config import get_settings

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "agents" / "evaluation" / "datasets" / "investment_rag_v1.json"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-below", type=float, default=0.8)
    return parser.parse_args()


async def _run(arguments: argparse.Namespace) -> int:
    settings = get_settings()
    embeddings = create_embedding_model()
    if embeddings is None:
        raise RuntimeError(
            "RAG embedding client is unavailable. Check RAG_ENABLED, "
            "RAG_EMBEDDING_PROVIDER, the provider API key, and its installed dependency."
        )
    retriever = HybridRAGRetriever(embeddings)
    report = await evaluate_retriever(retriever, load_retrieval_benchmark(arguments.dataset))
    payload = report.to_dict()
    provider = settings.rag_embedding_provider.strip().casefold()
    payload["embedding_provider"] = provider
    payload["embedding_model"] = (
        settings.openai_embedding_model
        if provider == "openai"
        else settings.upstage_embedding_model
    )
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    print(rendered)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered + "\n", encoding="utf-8")
    summary = payload["summary"]
    metrics = (
        summary["context_precision"],
        summary["context_recall"],
        summary["mean_reciprocal_rank"],
        summary["ndcg"],
    )
    return 0 if min(metrics) >= arguments.fail_below else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run(_arguments())))
