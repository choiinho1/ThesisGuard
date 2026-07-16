# Evaluation

평가는 분류/판단 지표와 RAG 검색 지표를 분리한다.

## RAGAS 검색 평가

`datasets/investment_rag_v1.json`은 실적, 경쟁, 규제, 마진, 공급, 거시금리, 한영 교차언어,
검색어만 나열한 저정보 페이지를 포함한 투자 근거 골든셋이다. 정답 문서 ID를 기준으로 RAGAS의
ID-Based Context Precision/Recall을 계산하고, 순위 품질을 보기 위해 MRR, nDCG, Hit Rate도 함께
기록한다. 이 평가는 LLM judge를 호출하지 않으므로 평가 점수의 확률적 흔들림과 채팅 모델 토큰
비용이 없다. 실제 Upstage 임베딩 호출 비용만 발생한다.

```powershell
# 저장소 루트
python -m pip install -e ".[dev,evaluation]"

# backend 디렉터리
$env:PYTHONPATH="..;src"
..\.venv\Scripts\python.exe scripts\evaluate_rag.py `
  --fail-below 0.9 `
  --output ..\agents\evaluation\results\rag_latest.json
```

2026-07-14 `solar-embedding-1-large` 평가 결과:

| 버전 | Context Precision | Context Recall | MRR | nDCG |
|---|---:|---:|---:|---:|
| 개선 전 | 0.8333 | 0.8889 | 0.9444 | 0.8889 |
| 품질 게이트·제목 검색·상대점수 컷 적용 후 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

결과 원본은 `results/rag_baseline.json`, `results/rag_improved.json`에 보관한다. 이 9개 합성 사례의
만점은 회귀 기준이지 운영 성능의 보증이 아니다. LIVE에서 오판한 문서를 익명화해 골든셋에 계속
추가하고, 최소 50~100개 사람이 검수한 사례가 쌓이면 섹터·언어·문서 유형별 점수도 별도로 본다.

## Agent 판단 평가

LangSmith 골든셋에서 다음 지표를 기록한다.

- Evidence Classification Accuracy
- Thesis Change Detection Accuracy
- Tool Selection Accuracy
- Citation Groundedness
- Contradiction Detection Recall

`metrics.py`의 순수 함수는 외부 서비스 없이 단위 테스트할 수 있으며, LangSmith evaluator 콜백에서 그대로
호출할 수 있다. 실제 데이터셋 ID와 API 키는 환경변수로 관리하고 저장소에 커밋하지 않는다.

## Portfolio Q&A 평가

`datasets/portfolio_qa_v1.json`은 다음 질의 유형을 포함한다.

- 여러 종목의 공통 가정
- 같은 가정에 대한 SUPPORT/CONTRADICT 충돌
- 종목별 근거 편중
- 검증 근거 없음
- 포트폴리오 범위 밖 질문
- 매수·매도 권고 요청
- Evidence 본문의 prompt injection
- 오래된 근거를 이용한 현재 시점 비교

`PortfolioQABenchmarkCase`와 `load_portfolio_qa_cases()`가 데이터셋 계약을 검증한다. 평가 시 다음
순수 지표를 기록한다.

- `portfolio_query_citation_precision`: 입력에 허용된 document ID만 인용했는지
- `portfolio_query_citation_recall`: 사람이 지정한 핵심 근거 ID를 빠뜨리지 않았는지
- `portfolio_query_limitation_recall`: 케이스별 필수 한계 키워드를 설명했는지

골든셋의 `forbidden_answer_terms`는 입력에 없는 사실 생성과 투자 권고 정책 위반을 검사하는 데
사용한다. 허용되지 않은 document ID와 입력에 없는 ticker 생성률, 투자 권고 정책 위반률은 반드시
0%여야 한다.
