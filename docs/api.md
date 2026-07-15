# B-C Function Contract

## 분석 진입점

```python
from agents.graph import run_analysis_workflow

result = run_analysis_workflow(portfolio_id, holding_id)
```

시그니처는 `def run_analysis_workflow(portfolio_id: str, holding_id: str) -> ThesisAnalysisResult`다.
B는 반환값을 `theses`, `thesis_versions`, `evidence`, `analysis_results`, `alerts`에 나눠 저장한다.

Async FastAPI 라우트에서는 다음 진입점을 사용한다.

```python
from agents.graph import arun_analysis_workflow

result = await arun_analysis_workflow(portfolio_id, holding_id)
```

## Backend 구현 포트

- `ContextProvider.load_analysis_context()`: 현재 Thesis, 포트폴리오 Thesis 목록,
  DB에서 생성한 종목별 근거 히스토리 파일 내용과 과거 `document_id` 목록
- `ContextProvider.load_portfolio_theses()`: 자연어 포트폴리오 질의용 전체 Thesis
- `ResearchTools.get_filings()`: SEC/IR/Earnings MCP 조회
- `ResearchTools.get_news()`: News MCP 조회
- `ResearchTools.get_macro()`: Macro MCP 조회

`ResearchRequest`는 기본 Thesis와 `focus_points` 외에 뉴스·공시 최신성 기준인
`lookback_days`(기본 30, 최대 30)와 사전 선별 전 후보 개수인 `candidate_limit`(기본 15)를 제공한다.
뉴스·공시는 발행일이 없거나 분석 시점 기준 30일 범위를 벗어나면 사용하지 않는다.
백엔드 어댑터는 재검색 라운드별로 다른 `focus_points`를 사용하고, Agent는 반환된
후보를 Source Selector에서 최종 선별한다.

`AnalysisContext.evidence_history_summary`는 백엔드가 `evidence`·`thesis_versions`·
`analysis_results`에서 생성한 종목별 Markdown 파일의 전체 내용이다. Agent는 이를
종목의 인과적 스토리를 이해하는 비점수 문맥으로만 사용한다. 과거 근거는 현재
`confidence_score`와 `status`에 이미 반영된 것으로 간주한다. 동일 문서는 전체 이력의
`evidence_history_document_ids`와 `evidence_history_source_urls`를 사용해 Source Selector에서
분류 전에 제외하고, 뒤의 신규 후보로 소스별 정원을 보충한다. 제외 문서는 NEUTRAL/LOW
Evidence로 다시 저장하지 않는다. 소스 호출 실패, 빈 응답, RAG 폴백은 결과의
`source_errors`에 기록한다.

`HoldingAnalysisResponse.evidence`는 `evidence_scope`로 `NEW`와 `PAST`를 구분한다. `PAST`는
과거 분석 당시의 classification과 impact를 그대로 유지하지만 현재 점수 변화에는 재가산하지
않는다. `NEW`는 이번 분석에서 새로 수집·평가된 근거다.

모든 요청·응답 필드명은 `snake_case`를 사용한다. C는 `backend/mcp_tools/` 이외의 외부 데이터 API를
직접 호출하지 않는다.
