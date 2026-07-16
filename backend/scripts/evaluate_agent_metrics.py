"""Run live evidence-classification, citation, latency, and alert-policy evaluation."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path
from typing import Any

from agents.evaluation.agent_benchmark import (
    classification_metrics,
    evaluate_alert_policy,
    excerpt_grounded,
    load_agent_metric_labels,
    percentile,
    validate_label_coverage,
)
from agents.evaluation.rag_benchmark import load_retrieval_benchmark
from agents.model import LangChainAnalysisModel
from agents.runnable_context import use_model_runnable_config

from thesisguard_backend.agent_adapters import create_chat_model
from thesisguard_backend.config import get_settings
from thesisguard_backend.observability import (
    get_langfuse_client,
    observe_llm_operation,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RETRIEVAL_DATASET = (
    ROOT / "agents" / "evaluation" / "datasets" / "investment_rag_v1.json"
)
DEFAULT_LABELS = ROOT / "agents" / "evaluation" / "datasets" / "agent_metrics_v1.json"
DEFAULT_OUTPUT = ROOT / "agents" / "evaluation" / "results" / "agent_metrics_live.json"
DEFAULT_TRACE_NAME = "thesisguard.evidence-classification-eval-v1-20260716-full"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieval-dataset", type=Path, default=DEFAULT_RETRIEVAL_DATASET)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--trace-name", default=DEFAULT_TRACE_NAME)
    return parser.parse_args()


async def _evaluate_one(
    *,
    model: LangChainAnalysisModel,
    semaphore: asyncio.Semaphore,
    case,
    document,
    expected: str,
    trace_name: str,
) -> dict[str, Any]:
    async with semaphore:
        started = time.perf_counter()
        try:
            with observe_llm_operation(
                trace_name,
                user_id="local-evaluation",
                session_id=f"agent-metrics-v1:{case.case_id}",
                input={"case_id": case.case_id, "document_id": document.document_id},
                metadata={
                    "dataset": "agent-metrics-v1",
                    "case_id": case.case_id,
                    "document_id": document.document_id,
                },
                tags=["evaluation", "evidence-classification"],
            ) as trace:
                with use_model_runnable_config(trace.runnable_config):
                    assessment = await model.classify_evidence(case.thesis, document)
                grounded = excerpt_grounded(assessment.source_excerpt, document.content)
                trace.set_output(
                    {
                        "classification": assessment.classification.value,
                        "source_excerpt_grounded": grounded,
                    }
                )
            return {
                "case_id": case.case_id,
                "document_id": document.document_id,
                "expected": expected,
                "predicted": assessment.classification.value,
                "source_excerpt": assessment.source_excerpt,
                "content_snippet": assessment.content_snippet,
                "source_excerpt_grounded": grounded,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001 - one failed model call must not abort the benchmark
            return {
                "case_id": case.case_id,
                "document_id": document.document_id,
                "expected": expected,
                "predicted": "ERROR",
                "source_excerpt": None,
                "content_snippet": None,
                "source_excerpt_grounded": False,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "error": f"{type(exc).__name__}: {exc}"[:500],
            }


async def _run(arguments: argparse.Namespace) -> int:
    labels = load_agent_metric_labels(arguments.labels)
    validate_label_coverage(labels, arguments.retrieval_dataset)
    cases = load_retrieval_benchmark(arguments.retrieval_dataset)
    settings = get_settings()
    model = LangChainAnalysisModel(create_chat_model())
    semaphore = asyncio.Semaphore(arguments.concurrency)

    tasks = []
    for case in cases:
        for document in case.documents:
            tasks.append(
                _evaluate_one(
                    model=model,
                    semaphore=semaphore,
                    case=case,
                    document=document,
                    expected=labels.classification_labels[case.case_id][
                        document.document_id
                    ].value,
                    trace_name=arguments.trace_name,
                )
            )
    if arguments.limit is not None:
        tasks = tasks[: arguments.limit]

    started = time.perf_counter()
    rows = await asyncio.gather(*tasks)
    total_seconds = time.perf_counter() - started
    client = get_langfuse_client()
    if client is not None:
        client.flush()

    expected = [row["expected"] for row in rows]
    predicted = [row["predicted"] for row in rows]
    classification = classification_metrics(expected, predicted)
    latencies = [float(row["latency_ms"]) for row in rows]
    grounded = sum(bool(row["source_excerpt_grounded"]) for row in rows)
    successful = sum(row["error"] is None for row in rows)
    report = {
        "metadata": {
            "dataset_id": labels.dataset_id,
            "labeling_method": labels.labeling_method,
            "model_provider": settings.llm_provider,
            "model": settings.llm_model,
            "trace_name": arguments.trace_name,
            "concurrency": arguments.concurrency,
            "wall_clock_seconds": round(total_seconds, 2),
        },
        "evidence_classification": classification,
        "citation_groundedness": {
            "definition": "선택된 source_excerpt의 모든 구간이 원문에 그대로 존재하는 비율",
            "grounded": grounded,
            "samples": len(rows),
            "rate": round(grounded / len(rows), 4) if rows else 0.0,
        },
        "classification_latency": {
            "samples": len(latencies),
            "mean_ms": round(statistics.fmean(latencies), 2),
            "p50_ms": round(percentile(latencies, 0.50), 2),
            "p95_ms": round(percentile(latencies, 0.95), 2),
        },
        "execution": {
            "successful": successful,
            "failed": len(rows) - successful,
            "success_rate": round(successful / len(rows), 4) if rows else 0.0,
        },
        "alert_policy": evaluate_alert_policy(labels.alert_cases),
        "langfuse_cost": {
            "status": "pending_observations_query",
            "trace_name": arguments.trace_name,
            "note": "Langfuse flush 후 GENERATION observation의 totalCost를 trace별 합산한다.",
        },
        "cases": rows,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = {key: value for key, value in report.items() if key != "cases"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote {arguments.output}")
    return 0 if successful == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run(_arguments())))
