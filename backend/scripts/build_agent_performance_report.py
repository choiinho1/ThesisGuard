"""Build presentation artifacts for ThesisGuard's non-RAG agent metrics."""

# ruff: noqa: E501 - long Korean presentation copy is intentionally kept intact.

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "agents" / "evaluation" / "results"
DEFAULT_LIVE = RESULTS / "agent_metrics_live.json"
DEFAULT_LANGFUSE = RESULTS / "langfuse_agent_metrics_2026-07-16.json"
DEFAULT_CSV = RESULTS / "agent_performance_metrics_2026-07-16.csv"
DEFAULT_JSON = RESULTS / "agent_performance_metrics_2026-07-16.json"
DEFAULT_MARKDOWN = ROOT / "docs" / "AGENT_PERFORMANCE_METRICS_REPORT.md"
DEFAULT_SVG = ROOT / "docs" / "assets" / "agent_performance_metrics_chart.svg"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", type=Path, default=DEFAULT_LIVE)
    parser.add_argument("--langfuse", type=Path, default=DEFAULT_LANGFUSE)
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--svg-output", type=Path, default=DEFAULT_SVG)
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _metrics(live: dict[str, Any], langfuse: dict[str, Any]) -> list[dict[str, Any]]:
    classification = live["evidence_classification"]
    citation = live["citation_groundedness"]
    alert = live["alert_policy"]
    latency = live["classification_latency"]
    execution = live["execution"]
    classification_cost = langfuse["evidence_classification_evaluation"]
    analysis = langfuse["holding_analysis_observations"]
    return [
        {"category": "AI judgment", "metric": "Evidence Classification Accuracy", "value": classification["accuracy"] * 100, "unit": "%", "sample": classification["samples"], "scope": "합성 사람 라벨 문서"},
        {"category": "AI judgment", "metric": "Evidence Classification Macro F1", "value": classification["macro_f1"] * 100, "unit": "%", "sample": classification["samples"], "scope": "SUPPORT/CONTRADICT/NEUTRAL"},
        {"category": "Grounding", "metric": "Source Excerpt Groundedness", "value": citation["rate"] * 100, "unit": "%", "sample": citation["samples"], "scope": "선택 구간의 원문 exact match"},
        {"category": "Alert", "metric": "Alert False Positive Rate", "value": alert["false_positive_rate"] * 100, "unit": "%", "sample": 8, "scope": "합성 no-alert 상태 전이"},
        {"category": "Alert", "metric": "Alert Recall", "value": alert["recall"] * 100, "unit": "%", "sample": 8, "scope": "합성 alert 상태 전이"},
        {"category": "Reliability", "metric": "Classification Success Rate", "value": execution["success_rate"] * 100, "unit": "%", "sample": classification["samples"], "scope": "실제 모델 호출"},
        {"category": "Latency", "metric": "Classification P95", "value": latency["p95_ms"] / 1000, "unit": "seconds", "sample": latency["samples"], "scope": "문서 1건"},
        {"category": "Latency", "metric": "Holding Analysis P50", "value": analysis["p50_latency_seconds"], "unit": "seconds", "sample": analysis["traces"], "scope": "보유종목 전체 분석"},
        {"category": "Latency", "metric": "Holding Analysis P95", "value": analysis["p95_latency_seconds"], "unit": "seconds", "sample": analysis["traces"], "scope": "보유종목 전체 분석"},
        {"category": "Cost", "metric": "Classification Mean Cost", "value": classification_cost["mean_cost_usd"], "unit": "USD", "sample": classification_cost["traces"], "scope": "문서 1건"},
        {"category": "Cost", "metric": "Holding Analysis Mean Cost", "value": analysis["mean_cost_usd"], "unit": "USD", "sample": analysis["traces"], "scope": "보유종목 전체 분석"},
        {"category": "Cost", "metric": "Holding Analysis P95 Cost", "value": analysis["p95_cost_usd"], "unit": "USD", "sample": analysis["traces"], "scope": "보유종목 전체 분석"},
    ]


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_svg(live: dict[str, Any], langfuse: dict[str, Any], path: Path) -> None:
    classification = live["evidence_classification"]
    citation = live["citation_groundedness"]
    alert = live["alert_policy"]
    latency = live["classification_latency"]
    analysis = langfuse["holding_analysis_observations"]
    cards = [
        ("증거 분류 정확도", f"{classification['accuracy'] * 100:.0f}%", "37개 사람 라벨 문서"),
        ("인용 원문 추적률", f"{citation['rate'] * 100:.0f}%", "source_excerpt exact match"),
        ("알림 오탐률", f"{alert['false_positive_rate'] * 100:.0f}%", "0/8 no-alert 사례"),
        ("문서 분류 P95", f"{latency['p95_ms'] / 1000:.2f}s", "실제 gpt-5.4-mini 호출"),
        ("전체 분석 P95", f"{analysis['p95_latency_seconds']:.2f}s", "development trace 9건"),
        ("분석 1건 평균 비용", f"${analysis['mean_cost_usd']:.4f}", "LLM generation 비용"),
    ]
    colors = ["#2563EB", "#0891B2", "#059669", "#7C3AED", "#EA580C", "#0F766E"]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675">',
        '<rect width="1200" height="675" fill="#F8FAFC"/>',
        '<text x="70" y="72" font-family="Pretendard, Noto Sans KR, Arial" font-size="34" font-weight="700" fill="#0F172A">AI 판단·운영 성과 지표</text>',
        '<text x="70" y="108" font-family="Pretendard, Noto Sans KR, Arial" font-size="17" fill="#475569">RAG 검색 지표와 분리한 실측 결과 · 2026-07-16</text>',
    ]
    for index, ((title, value, note), color) in enumerate(zip(cards, colors, strict=True)):
        column = index % 3
        row = index // 3
        x = 70 + column * 375
        y = 145 + row * 235
        parts.extend(
            [
                f'<rect x="{x}" y="{y}" width="340" height="195" rx="20" fill="#FFFFFF" stroke="#E2E8F0"/>',
                f'<rect x="{x}" y="{y}" width="8" height="195" rx="4" fill="{color}"/>',
                f'<text x="{x + 34}" y="{y + 47}" font-family="Pretendard, Noto Sans KR, Arial" font-size="18" font-weight="600" fill="#475569">{title}</text>',
                f'<text x="{x + 34}" y="{y + 116}" font-family="Arial" font-size="46" font-weight="700" fill="{color}">{value}</text>',
                f'<text x="{x + 34}" y="{y + 158}" font-family="Pretendard, Noto Sans KR, Arial" font-size="15" fill="#64748B">{note}</text>',
            ]
        )
    parts.extend(
        [
            '<text x="70" y="646" font-family="Pretendard, Noto Sans KR, Arial" font-size="14" fill="#64748B">※ 합성 골든셋 및 development 관측 표본 결과이며 운영 성능 보증이 아님</text>',
            "</svg>",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def _render(live: dict[str, Any], langfuse: dict[str, Any]) -> str:
    classification = live["evidence_classification"]
    citation = live["citation_groundedness"]
    alert = live["alert_policy"]
    latency = live["classification_latency"]
    execution = live["execution"]
    classification_cost = langfuse["evidence_classification_evaluation"]
    analysis = langfuse["holding_analysis_observations"]
    return rf"""# ThesisGuard 비-RAG 에이전트 성과 지표

> 측정일: 2026-07-16  
> 모델: `gpt-5.4-mini`  
> RAG 검색 성능과 별도로 측정한 AI 판단·알림·운영 지표

## 발표용 핵심 결과표

| 영역 | 지표 | 결과 | 표본 및 범위 |
|---|---|---:|---|
| AI 판단 | Evidence Classification Accuracy | {classification['accuracy'] * 100:.2f}% | 사람 라벨 합성 문서 {classification['samples']}건 |
| AI 판단 | Macro F1 | {classification['macro_f1'] * 100:.2f}% | SUPPORT 9 · CONTRADICT 8 · NEUTRAL 20 |
| 인용 | Source Excerpt Groundedness | {citation['rate'] * 100:.2f}% | {citation['grounded']}/{citation['samples']}건 |
| 알림 | False Positive Rate | {alert['false_positive_rate'] * 100:.2f}% | no-alert 사례 8건 중 FP 0건 |
| 알림 | Alert Recall | {alert['recall'] * 100:.2f}% | alert 사례 8건 중 TP 8건 |
| 안정성 | 모델 호출 성공률 | {execution['success_rate'] * 100:.2f}% | {execution['successful']}/{classification['samples']}건 |
| 속도 | 문서 1건 분류 p50 / p95 | {latency['p50_ms'] / 1000:.2f}s / {latency['p95_ms'] / 1000:.2f}s | 실제 모델 호출 {latency['samples']}건 |
| 속도 | 보유종목 전체 분석 p50 / p95 | {analysis['p50_latency_seconds']:.2f}s / {analysis['p95_latency_seconds']:.2f}s | development trace {analysis['traces']}건 |
| 비용 | 문서 1건 분류 평균 / p95 | ${classification_cost['mean_cost_usd']:.5f} / ${classification_cost['p95_cost_usd']:.5f} | Langfuse trace {classification_cost['traces']}건 |
| 비용 | 보유종목 전체 분석 평균 / p95 | ${analysis['mean_cost_usd']:.5f} / ${analysis['p95_cost_usd']:.5f} | development trace {analysis['traces']}건 |

## 지표별 의미

- **증거 분류 정확도**: 투자 논리와 문서를 비교해 SUPPORT·CONTRADICT·NEUTRAL을 사람 라벨과 동일하게 판정한 비율입니다.
- **Macro F1**: 문서 수가 많은 NEUTRAL 클래스에 정확도가 치우치지 않았는지 세 클래스 F1을 동일 비중으로 평균한 값입니다.
- **Source Excerpt Groundedness**: 모델이 선택한 근거 구간이 실제 원문에 그대로 존재하는지를 검사합니다. 생성된 한국어 요약의 모든 문장이 의미적으로 참이라는 보증과는 다릅니다.
- **알림 오탐률**: 알림을 보내지 않아야 하는 상태 전이 중 잘못 알림을 발생시킨 비율입니다. 현재 값은 규칙 기반 정책의 합성 상태 전이 적합도이며 실제 사용자 피드백 기반 오탐률은 아닙니다.
- **전체 분석 지연·비용**: 자료수집부터 판단까지의 `thesisguard.analyze-holding` root trace 지연과 그 trace에 속한 LLM generation 비용의 합계입니다.

## 발표에서 그대로 사용할 문구

> RAG 검색 품질과 별도로 AI 판단 성능을 평가했습니다. 사람 라벨 문서 37건에서 증거 분류 Accuracy와 Macro F1이 모두 100%였고, 선택한 인용 구간 37건도 모두 실제 원문에서 확인됐습니다. 규칙 기반 알림 정책은 16개 상태 전이 사례에서 오탐 0건, 누락 0건을 기록했습니다. 실제 보유종목 분석 9건의 p95 지연은 43.51초, 건당 평균 LLM 비용은 약 0.049달러였습니다.

## 반드시 함께 밝힐 한계

- 37개 문서는 합성 골든셋이며 독립적인 실사용 블라인드 테스트셋이 아닙니다.
- 인용 100%는 선택한 원문 구간의 추적 가능성을 뜻하며 생성 요약 전체의 의미적 사실성을 보증하지 않습니다.
- 알림 오탐률 0%는 사람이 정의한 16개 상태 전이 정책 테스트 결과입니다. 실제 사용자 알림 만족도는 별도 수집이 필요합니다.
- 전체 분석 표본은 9건으로 작고 동일 입력 반복 부하시험이 아닙니다. p95 운영 SLA 확정에는 30건 이상 반복 측정이 필요합니다.
- 비용은 LLM generation만 포함하며 외부 데이터 공급자와 서버 비용은 제외합니다.

## 재현 방법

`backend` 디렉터리에서 실행합니다.

```powershell
$env:PYTHONPATH="..;src"
..\.venv\Scripts\python.exe scripts\evaluate_agent_metrics.py --concurrency 3
..\.venv\Scripts\python.exe scripts\build_agent_performance_report.py
```

산출물:

- `docs/AGENT_PERFORMANCE_METRICS_REPORT.md`
- `docs/assets/agent_performance_metrics_chart.svg`
- `agents/evaluation/results/agent_metrics_live.json`
- `agents/evaluation/results/langfuse_agent_metrics_2026-07-16.json`
- `agents/evaluation/results/agent_performance_metrics_2026-07-16.csv`
- `agents/evaluation/results/agent_performance_metrics_2026-07-16.json`
"""


def main() -> int:
    arguments = _arguments()
    live = _load(arguments.live)
    langfuse = _load(arguments.langfuse)
    rows = _metrics(live, langfuse)
    _write_csv(rows, arguments.csv_output)
    _write_svg(live, langfuse, arguments.svg_output)
    arguments.json_output.parent.mkdir(parents=True, exist_ok=True)
    arguments.json_output.write_text(
        json.dumps(
            {
                "measurement_date": langfuse["measurement_date"],
                "metrics": rows,
                "evidence_classification": live["evidence_classification"],
                "citation_groundedness": live["citation_groundedness"],
                "alert_policy": live["alert_policy"],
                "classification_latency": live["classification_latency"],
                "cost_and_end_to_end": langfuse,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    arguments.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    arguments.markdown_output.write_text(_render(live, langfuse), encoding="utf-8")
    print(f"Wrote {arguments.markdown_output}")
    print(f"Wrote {arguments.csv_output}")
    print(f"Wrote {arguments.json_output}")
    print(f"Wrote {arguments.svg_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
