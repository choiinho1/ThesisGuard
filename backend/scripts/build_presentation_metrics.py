"""Build presentation-ready ThesisGuard benchmark artifacts from raw results."""

# ruff: noqa: E501 - long Korean presentation copy is kept readable in generated Markdown.

from __future__ import annotations

import argparse
import csv
import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "agents" / "evaluation" / "results"
DEFAULT_BASELINE = RESULTS_DIR / "rag_baseline.json"
DEFAULT_IMPROVED = RESULTS_DIR / "rag_improved.json"
DEFAULT_VERIFICATION = RESULTS_DIR / "verification_2026-07-16.json"
DEFAULT_JSON = RESULTS_DIR / "presentation_metrics_2026-07-16.json"
DEFAULT_CSV = RESULTS_DIR / "presentation_metrics_2026-07-16.csv"
DEFAULT_MARKDOWN = ROOT / "docs" / "PRESENTATION_METRICS_REPORT.md"
DEFAULT_SVG = ROOT / "docs" / "assets" / "presentation_metrics_chart.svg"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--improved", type=Path, default=DEFAULT_IMPROVED)
    parser.add_argument("--verification", type=Path, default=DEFAULT_VERIFICATION)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--svg-output", type=Path, default=DEFAULT_SVG)
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _percentile(values: Sequence[float], percentile: float) -> float:
    """Return a linearly interpolated percentile, equivalent to NumPy's default."""

    if not values:
        raise ValueError("At least one value is required")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction)


def _is_perfect(case: dict[str, Any]) -> bool:
    keys = ("context_precision", "context_recall", "reciprocal_rank", "ndcg")
    return all(math.isclose(float(case[key]), 1.0) for key in keys)


def _rate_delta(baseline: float, improved: float) -> dict[str, float]:
    return {
        "baseline": round(baseline, 4),
        "improved": round(improved, 4),
        "delta_percentage_points": round((improved - baseline) * 100, 2),
        "relative_change_percent": round(
            ((improved - baseline) / baseline) * 100 if baseline else 0.0, 2
        ),
    }


def _latency_delta(baseline: float, improved: float) -> dict[str, float]:
    return {
        "baseline_ms": round(baseline, 2),
        "improved_ms": round(improved, 2),
        "delta_ms": round(improved - baseline, 2),
        "relative_change_percent": round(
            ((improved - baseline) / baseline) * 100 if baseline else 0.0, 2
        ),
    }


def _build_report(
    baseline: dict[str, Any], improved: dict[str, Any], verification: dict[str, Any]
) -> dict[str, Any]:
    baseline_cases = {case["case_id"]: case for case in baseline["cases"]}
    improved_cases = {case["case_id"]: case for case in improved["cases"]}
    if baseline_cases.keys() != improved_cases.keys():
        raise ValueError("Baseline and improved reports must contain the same case IDs")

    baseline_summary = baseline["summary"]
    improved_summary = improved["summary"]
    metric_keys = {
        "context_precision": "Context Precision",
        "context_recall": "Context Recall",
        "mean_reciprocal_rank": "MRR",
        "ndcg": "nDCG",
        "hit_rate": "Hit Rate",
    }
    quality = {
        label: _rate_delta(
            float(baseline_summary[key]),
            float(improved_summary[key]),
        )
        for key, label in metric_keys.items()
    }

    case_count = len(baseline_cases)
    baseline_perfect = sum(_is_perfect(case) for case in baseline_cases.values())
    improved_perfect = sum(_is_perfect(case) for case in improved_cases.values())
    resolved_cases = [
        case_id
        for case_id in baseline_cases
        if not _is_perfect(baseline_cases[case_id]) and _is_perfect(improved_cases[case_id])
    ]
    quality["Perfect Case Rate"] = _rate_delta(
        baseline_perfect / case_count, improved_perfect / case_count
    )

    baseline_latencies = [float(case["latency_ms"]) for case in baseline_cases.values()]
    improved_latencies = [float(case["latency_ms"]) for case in improved_cases.values()]
    latency = {
        "Mean": _latency_delta(
            float(baseline_summary["mean_latency_ms"]),
            float(improved_summary["mean_latency_ms"]),
        ),
        "P50": _latency_delta(
            _percentile(baseline_latencies, 0.50),
            _percentile(improved_latencies, 0.50),
        ),
        "P95": _latency_delta(
            _percentile(baseline_latencies, 0.95),
            _percentile(improved_latencies, 0.95),
        ),
    }

    test_passed = sum(int(suite["passed"]) for suite in verification["test_suites"])
    test_total = sum(int(suite["total"]) for suite in verification["test_suites"])
    static_passed = sum(bool(check["passed"]) for check in verification["static_checks"])
    static_total = len(verification["static_checks"])

    return {
        "metadata": {
            "generated_for": "ThesisGuard project presentation",
            "measurement_date": verification["measured_at"],
            "embedding_model": improved.get("embedding_model"),
            "benchmark_cases": case_count,
            "source_files": [
                "agents/evaluation/results/rag_baseline.json",
                "agents/evaluation/results/rag_improved.json",
                "agents/evaluation/results/verification_2026-07-16.json",
            ],
        },
        "retrieval_quality": quality,
        "hard_case_resolution": {
            "baseline_imperfect_cases": case_count - baseline_perfect,
            "resolved_cases": len(resolved_cases),
            "resolution_rate": round(
                len(resolved_cases) / (case_count - baseline_perfect)
                if case_count != baseline_perfect
                else 1.0,
                4,
            ),
            "case_ids": resolved_cases,
        },
        "retrieval_latency": latency,
        "verification": {
            "tests_passed": test_passed,
            "tests_total": test_total,
            "test_pass_rate": round(test_passed / test_total, 4) if test_total else 0.0,
            "static_checks_passed": static_passed,
            "static_checks_total": static_total,
            "test_suites": verification["test_suites"],
            "static_checks": verification["static_checks"],
        },
        "interpretation": {
            "proven": [
                "동일한 9개 합성 회귀 사례에서 검색 품질 지표가 모두 100%에 도달했다.",
                "기존에 완벽히 처리하지 못한 어려운 사례 3건을 모두 해결했다.",
                "에이전트 및 백엔드 테스트 141개와 프런트 정적 검사 2종을 통과했다.",
            ],
            "not_yet_proven": [
                "9개 사례 결과만으로 실제 운영 정확도 100%를 주장할 수 없다.",
                "평균 검색시간은 감소했지만 현재 표본의 P50과 P95는 개선되지 않아 속도 향상이 확정적이지 않다.",
                "전체 에이전트 분석의 P95, 판단 정확도, 알림 오탐률, 건당 비용은 추가 측정이 필요하다.",
            ],
        },
        "next_metrics": [
            {
                "metric": "Evidence Classification Macro F1",
                "target": ">= 80%",
                "required_data": "사람이 분류한 SUPPORT/CONTRADICT/NEUTRAL/UNCERTAIN 50~100건",
            },
            {
                "metric": "Contradiction Detection Recall",
                "target": ">= 90%",
                "required_data": "반박 근거 문서 ID가 표시된 골든셋",
            },
            {
                "metric": "Citation Groundedness",
                "target": ">= 95%",
                "required_data": "생성 인용과 원문 대응 라벨",
            },
            {
                "metric": "Alert False Positive Rate",
                "target": "<= 10%",
                "required_data": "알림 필요/불필요 사람 판정",
            },
            {
                "metric": "End-to-End Analysis P95",
                "target": "기준선 측정 후 10~20% 단축",
                "required_data": "워밍업 제외 동일 시나리오 30회 이상",
            },
            {
                "metric": "Cost per Analysis",
                "target": "팀 비용 상한 확정 후 적용",
                "required_data": "Langfuse 토큰 및 모델별 단가",
            },
        ],
    }


def _write_csv(report: dict[str, Any], path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for metric, values in report["retrieval_quality"].items():
        rows.append(
            {
                "category": "retrieval_quality",
                "metric": metric,
                "unit": "percent",
                "baseline": round(values["baseline"] * 100, 2),
                "improved": round(values["improved"] * 100, 2),
                "delta": values["delta_percentage_points"],
                "relative_change_percent": values["relative_change_percent"],
                "status": "measured",
            }
        )
    for metric, values in report["retrieval_latency"].items():
        rows.append(
            {
                "category": "retrieval_latency",
                "metric": metric,
                "unit": "ms",
                "baseline": values["baseline_ms"],
                "improved": values["improved_ms"],
                "delta": values["delta_ms"],
                "relative_change_percent": values["relative_change_percent"],
                "status": "measured_small_sample",
            }
        )
    verification = report["verification"]
    rows.append(
        {
            "category": "verification",
            "metric": "Automated Test Pass Rate",
            "unit": "percent",
            "baseline": "",
            "improved": round(verification["test_pass_rate"] * 100, 2),
            "delta": "",
            "relative_change_percent": "",
            "status": "measured",
        }
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_svg(report: dict[str, Any], path: Path) -> None:
    """Write a dependency-free 16:9 SVG chart suitable for presentation slides."""

    metrics = ["Context Precision", "Context Recall", "MRR", "nDCG"]
    labels = ["Precision", "Recall", "MRR", "nDCG"]
    chart_left = 110
    chart_top = 150
    chart_height = 330
    group_width = 245
    bar_width = 62
    baseline_color = "#94A3B8"
    improved_color = "#2563EB"
    quality = report["retrieval_quality"]
    verification = report["verification"]

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" '
        'viewBox="0 0 1200 675">',
        "<defs>",
        '<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">',
        '<feDropShadow dx="0" dy="4" stdDeviation="8" flood-opacity="0.12"/>',
        "</filter>",
        "</defs>",
        '<rect width="1200" height="675" fill="#F8FAFC"/>',
        '<text x="70" y="72" font-family="Pretendard, Noto Sans KR, Arial" '
        'font-size="34" font-weight="700" fill="#0F172A">RAG 검색 품질 개선</text>',
        '<text x="70" y="108" font-family="Pretendard, Noto Sans KR, Arial" '
        'font-size="17" fill="#475569">동일한 합성 회귀 사례 9건 · solar-embedding-1-large</text>',
    ]

    for tick in range(0, 101, 20):
        y = chart_top + chart_height - chart_height * tick / 100
        parts.extend(
            [
                f'<line x1="{chart_left}" y1="{y:.1f}" x2="1080" y2="{y:.1f}" '
                'stroke="#E2E8F0" stroke-width="1"/>',
                f'<text x="92" y="{y + 6:.1f}" text-anchor="end" '
                'font-family="Arial" font-size="14" fill="#64748B">'
                f"{tick}%</text>",
            ]
        )

    for index, (metric, label) in enumerate(zip(metrics, labels, strict=True)):
        group_x = chart_left + 55 + index * group_width
        baseline = quality[metric]["baseline"] * 100
        improved = quality[metric]["improved"] * 100
        baseline_height = chart_height * baseline / 100
        improved_height = chart_height * improved / 100
        baseline_y = chart_top + chart_height - baseline_height
        improved_y = chart_top + chart_height - improved_height
        parts.extend(
            [
                f'<rect x="{group_x}" y="{baseline_y:.1f}" width="{bar_width}" '
                f'height="{baseline_height:.1f}" rx="8" fill="{baseline_color}"/>',
                f'<rect x="{group_x + 78}" y="{improved_y:.1f}" width="{bar_width}" '
                f'height="{improved_height:.1f}" rx="8" fill="{improved_color}"/>',
                f'<text x="{group_x + bar_width / 2:.1f}" y="{baseline_y - 12:.1f}" '
                'text-anchor="middle" font-family="Arial" font-size="16" '
                f'font-weight="700" fill="#475569">{baseline:.1f}%</text>',
                f'<text x="{group_x + 78 + bar_width / 2:.1f}" y="{improved_y - 12:.1f}" '
                'text-anchor="middle" font-family="Arial" font-size="16" '
                f'font-weight="700" fill="#1D4ED8">{improved:.1f}%</text>',
                f'<text x="{group_x + 70}" y="520" text-anchor="middle" '
                'font-family="Pretendard, Noto Sans KR, Arial" font-size="17" '
                f'font-weight="600" fill="#334155">{label}</text>',
            ]
        )

    parts.extend(
        [
            '<rect x="760" y="36" width="150" height="38" rx="19" fill="#E2E8F0"/>',
            '<circle cx="784" cy="55" r="7" fill="#94A3B8"/>',
            '<text x="800" y="61" font-family="Pretendard, Noto Sans KR, Arial" '
            'font-size="15" fill="#334155">개선 전</text>',
            '<rect x="925" y="36" width="150" height="38" rx="19" fill="#DBEAFE"/>',
            '<circle cx="949" cy="55" r="7" fill="#2563EB"/>',
            '<text x="965" y="61" font-family="Pretendard, Noto Sans KR, Arial" '
            'font-size="15" fill="#1E3A8A">개선 후</text>',
            '<g filter="url(#shadow)">',
            '<rect x="70" y="565" width="500" height="76" rx="16" fill="#FFFFFF"/>',
            '<text x="98" y="597" font-family="Pretendard, Noto Sans KR, Arial" '
            'font-size="15" fill="#64748B">완벽 처리 사례</text>',
            '<text x="98" y="625" font-family="Pretendard, Noto Sans KR, Arial" '
            'font-size="25" font-weight="700" fill="#0F172A">6/9 → 9/9</text>',
            '<rect x="630" y="565" width="500" height="76" rx="16" fill="#FFFFFF"/>',
            '<text x="658" y="597" font-family="Pretendard, Noto Sans KR, Arial" '
            'font-size="15" fill="#64748B">자동화 테스트</text>',
            '<text x="658" y="625" font-family="Pretendard, Noto Sans KR, Arial" '
            f'font-size="25" font-weight="700" fill="#0F172A">{verification["tests_passed"]}/{verification["tests_total"]} 통과</text>',
            "</g>",
            "</svg>",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def _percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def _signed(value: float, suffix: str = "") -> str:
    return f"{value:+.2f}{suffix}"


def _render_markdown(report: dict[str, Any]) -> str:
    quality_rows = []
    for metric, values in report["retrieval_quality"].items():
        quality_rows.append(
            f"| {metric} | {_percent(values['baseline'])} | {_percent(values['improved'])} "
            f"| {_signed(values['delta_percentage_points'], '%p')} |"
        )

    latency_rows = []
    for metric, values in report["retrieval_latency"].items():
        latency_rows.append(
            f"| {metric} | {values['baseline_ms']:.2f} ms | {values['improved_ms']:.2f} ms "
            f"| {_signed(values['delta_ms'], ' ms')} "
            f"({_signed(values['relative_change_percent'], '%')}) |"
        )

    next_rows = []
    for item in report["next_metrics"]:
        next_rows.append(
            f"| {item['metric']} | {item['target']} | {item['required_data']} |"
        )

    hard_cases = report["hard_case_resolution"]
    verification = report["verification"]
    resolved_ids = ", ".join(f"`{case_id}`" for case_id in hard_cases["case_ids"])
    return rf"""# ThesisGuard 프로젝트 발표용 성과 지표

> 측정 기준일: {report['metadata']['measurement_date']}  
> 임베딩 모델: `{report['metadata']['embedding_model']}`  
> 평가 범위: 합성 RAG 회귀 사례 {report['metadata']['benchmark_cases']}건

## 1. 발표 슬라이드용 핵심 결과표

> 비-RAG 지표(증거 분류·인용·알림·전체 분석 p95·비용)는 `docs/AGENT_PERFORMANCE_METRICS_REPORT.md`에 별도로 정리되어 있습니다.

### 검색 품질

| 지표 | 개선 전 | 개선 후 | 변화 |
|---|---:|---:|---:|
{chr(10).join(quality_rows)}

- 완벽 처리 사례가 6/9건(66.67%)에서 9/9건(100%)으로 증가했습니다.
- 기존 실패 사례 {hard_cases['baseline_imperfect_cases']}건 중 {hard_cases['resolved_cases']}건을 해결해 어려운 사례 해결률 100%를 기록했습니다.
- 해결한 사례: {resolved_ids}

### 검색 지연시간

| 지표 | 개선 전 | 개선 후 | 변화 |
|---|---:|---:|---:|
{chr(10).join(latency_rows)}

평균은 9.21ms(2.47%) 감소했지만 P50과 P95는 증가했습니다. 따라서 현재 자료로는 “평균 검색시간이 소폭 감소했다”고만 표현하고, “전반적인 속도가 개선됐다”는 주장은 추가 반복 측정 전까지 보류합니다.

### 구현 안정성

| 검증 항목 | 결과 |
|---|---:|
| Agent 테스트 | {verification['test_suites'][0]['passed']}/{verification['test_suites'][0]['total']} 통과 |
| Backend 테스트 | {verification['test_suites'][1]['passed']}/{verification['test_suites'][1]['total']} 통과 |
| 전체 자동화 테스트 | {verification['tests_passed']}/{verification['tests_total']} 통과 ({_percent(verification['test_pass_rate'])}) |
| Frontend ESLint | 통과 |
| Frontend TypeScript 검사 | 통과 |

테스트 통과율은 현재 테스트가 다루는 범위의 회귀 안정성을 뜻하며, 실제 운영 정확도와는 구분해야 합니다.

## 2. 발표에서 그대로 사용할 문구

### 한 줄 요약

> 품질 게이트·제목 검색·상대점수 컷을 적용해 9개 RAG 회귀 사례의 Context Precision을 83.33%에서 100%로, Context Recall을 88.89%에서 100%로 개선했습니다.

### 20초 발표 멘트

> 동일한 9개 투자 근거 검색 사례로 개선 전후를 비교했습니다. Context Precision은 16.67%p, Context Recall은 11.11%p 상승했고, 기존에 실패했던 노이즈 및 하드 네거티브 사례 3건을 모두 해결했습니다. 또한 에이전트와 백엔드 자동화 테스트 총 {verification['tests_total']}개, 프런트엔드 정적 검사 2종을 모두 통과했습니다. 다만 9개 합성 사례의 만점은 회귀 성능이며 실서비스 정확도 100%를 의미하지는 않습니다.

### 슬라이드 그래프 추천

1. 묶은 세로 막대: Context Precision, Context Recall, MRR, nDCG의 개선 전·후 비교
2. 진행률 막대: 완벽 처리 사례 6/9 → 9/9
3. 검증 배지: `{verification['tests_passed']}/{verification['tests_total']} tests passed`, `ESLint passed`, `TypeScript passed`

차트 원본 데이터는 `agents/evaluation/results/presentation_metrics_2026-07-16.csv`를 사용하면 됩니다.
완성된 16:9 차트는 `docs/assets/presentation_metrics_chart.svg`입니다.

## 3. 해석 시 주의사항

- 현재 골든셋은 합성 사례 9건이므로 “운영 정확도 100%”라고 표현하지 않습니다.
- 같은 평가셋을 개선 과정에 사용했기 때문에 독립된 블라인드 테스트셋 검증이 필요합니다.
- 지연시간은 사례별 1회 측정값입니다. 워밍업 후 동일 사례를 30회 이상 반복해야 신뢰할 수 있는 P95가 나옵니다.
- 현재 지연시간은 RAG 문서 선택 구간만 포함하며 전체 에이전트 분석시간은 포함하지 않습니다.
- 테스트 통과 수는 정확도 사례 수와 합산하지 않습니다. 두 수치는 서로 다른 성과입니다.

## 4. 다음 발표 버전에서 추가할 지표

| 지표 | 권장 목표 | 필요한 데이터 |
|---|---:|---|
{chr(10).join(next_rows)}

## 5. 재현 방법

저장소 루트에서 실행합니다.

```powershell
.\.venv\Scripts\python.exe backend\scripts\build_presentation_metrics.py
```

입력 원본:

- `agents/evaluation/results/rag_baseline.json`
- `agents/evaluation/results/rag_improved.json`
- `agents/evaluation/results/verification_2026-07-16.json`

생성 결과:

- `docs/PRESENTATION_METRICS_REPORT.md`
- `agents/evaluation/results/presentation_metrics_2026-07-16.json`
- `agents/evaluation/results/presentation_metrics_2026-07-16.csv`
- `docs/assets/presentation_metrics_chart.svg`
"""


def main() -> int:
    arguments = _arguments()
    report = _build_report(
        _load(arguments.baseline),
        _load(arguments.improved),
        _load(arguments.verification),
    )

    arguments.json_output.parent.mkdir(parents=True, exist_ok=True)
    arguments.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_csv(report, arguments.csv_output)
    _write_svg(report, arguments.svg_output)
    arguments.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    arguments.markdown_output.write_text(_render_markdown(report), encoding="utf-8")

    print(f"Wrote {arguments.markdown_output}")
    print(f"Wrote {arguments.json_output}")
    print(f"Wrote {arguments.csv_output}")
    print(f"Wrote {arguments.svg_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
