# ThesisGuard 비-RAG 에이전트 성과 지표

> 측정일: 2026-07-16  
> 모델: `gpt-5.4-mini`  
> RAG 검색 성능과 별도로 측정한 AI 판단·알림·운영 지표

## 발표용 핵심 결과표

| 영역 | 지표 | 결과 | 표본 및 범위 |
|---|---|---:|---|
| AI 판단 | Evidence Classification Accuracy | 100.00% | 사람 라벨 합성 문서 37건 |
| AI 판단 | Macro F1 | 100.00% | SUPPORT 9 · CONTRADICT 8 · NEUTRAL 20 |
| 인용 | Source Excerpt Groundedness | 100.00% | 37/37건 |
| 알림 | False Positive Rate | 0.00% | no-alert 사례 8건 중 FP 0건 |
| 알림 | Alert Recall | 100.00% | alert 사례 8건 중 TP 8건 |
| 안정성 | 모델 호출 성공률 | 100.00% | 37/37건 |
| 속도 | 문서 1건 분류 p50 / p95 | 3.20s / 4.31s | 실제 모델 호출 37건 |
| 속도 | 보유종목 전체 분석 p50 / p95 | 23.13s / 43.51s | development trace 9건 |
| 비용 | 문서 1건 분류 평균 / p95 | $0.00272 / $0.00298 | Langfuse trace 37건 |
| 비용 | 보유종목 전체 분석 평균 / p95 | $0.04946 / $0.09299 | development trace 9건 |

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
