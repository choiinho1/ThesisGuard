# ThesisGuard 프로젝트 발표용 성과 지표

> 측정 기준일: 2026-07-16  
> 임베딩 모델: `solar-embedding-1-large`  
> 평가 범위: 합성 RAG 회귀 사례 9건

## 1. 발표 슬라이드용 핵심 결과표

> 비-RAG 지표(증거 분류·인용·알림·전체 분석 p95·비용)는 `docs/AGENT_PERFORMANCE_METRICS_REPORT.md`에 별도로 정리되어 있습니다.

### 검색 품질

| 지표 | 개선 전 | 개선 후 | 변화 |
|---|---:|---:|---:|
| Context Precision | 83.33% | 100.00% | +16.67%p |
| Context Recall | 88.89% | 100.00% | +11.11%p |
| MRR | 94.44% | 100.00% | +5.56%p |
| nDCG | 88.89% | 100.00% | +11.11%p |
| Hit Rate | 100.00% | 100.00% | +0.00%p |
| Perfect Case Rate | 66.67% | 100.00% | +33.33%p |

- 완벽 처리 사례가 6/9건(66.67%)에서 9/9건(100%)으로 증가했습니다.
- 기존 실패 사례 3건 중 3건을 해결해 어려운 사례 해결률 100%를 기록했습니다.
- 해결한 사례: `amzn-title-and-hard-negatives`, `coin-query-coverage-noise`, `nflx-abstain-from-noise`

### 검색 지연시간

| 지표 | 개선 전 | 개선 후 | 변화 |
|---|---:|---:|---:|
| Mean | 373.01 ms | 363.80 ms | -9.21 ms (-2.47%) |
| P50 | 322.12 ms | 324.89 ms | +2.77 ms (+0.86%) |
| P95 | 551.72 ms | 582.00 ms | +30.28 ms (+5.49%) |

평균은 9.21ms(2.47%) 감소했지만 P50과 P95는 증가했습니다. 따라서 현재 자료로는 “평균 검색시간이 소폭 감소했다”고만 표현하고, “전반적인 속도가 개선됐다”는 주장은 추가 반복 측정 전까지 보류합니다.

### 구현 안정성

| 검증 항목 | 결과 |
|---|---:|
| Agent 테스트 | 76/76 통과 |
| Backend 테스트 | 69/69 통과 |
| 전체 자동화 테스트 | 145/145 통과 (100.00%) |
| Frontend ESLint | 통과 |
| Frontend TypeScript 검사 | 통과 |

테스트 통과율은 현재 테스트가 다루는 범위의 회귀 안정성을 뜻하며, 실제 운영 정확도와는 구분해야 합니다.

## 2. 발표에서 그대로 사용할 문구

### 한 줄 요약

> 품질 게이트·제목 검색·상대점수 컷을 적용해 9개 RAG 회귀 사례의 Context Precision을 83.33%에서 100%로, Context Recall을 88.89%에서 100%로 개선했습니다.

### 20초 발표 멘트

> 동일한 9개 투자 근거 검색 사례로 개선 전후를 비교했습니다. Context Precision은 16.67%p, Context Recall은 11.11%p 상승했고, 기존에 실패했던 노이즈 및 하드 네거티브 사례 3건을 모두 해결했습니다. 또한 에이전트와 백엔드 자동화 테스트 총 145개, 프런트엔드 정적 검사 2종을 모두 통과했습니다. 다만 9개 합성 사례의 만점은 회귀 성능이며 실서비스 정확도 100%를 의미하지는 않습니다.

### 슬라이드 그래프 추천

1. 묶은 세로 막대: Context Precision, Context Recall, MRR, nDCG의 개선 전·후 비교
2. 진행률 막대: 완벽 처리 사례 6/9 → 9/9
3. 검증 배지: `145/145 tests passed`, `ESLint passed`, `TypeScript passed`

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
| Evidence Classification Macro F1 | >= 80% | 사람이 분류한 SUPPORT/CONTRADICT/NEUTRAL/UNCERTAIN 50~100건 |
| Contradiction Detection Recall | >= 90% | 반박 근거 문서 ID가 표시된 골든셋 |
| Citation Groundedness | >= 95% | 생성 인용과 원문 대응 라벨 |
| Alert False Positive Rate | <= 10% | 알림 필요/불필요 사람 판정 |
| End-to-End Analysis P95 | 기준선 측정 후 10~20% 단축 | 워밍업 제외 동일 시나리오 30회 이상 |
| Cost per Analysis | 팀 비용 상한 확정 후 적용 | Langfuse 토큰 및 모델별 단가 |

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
