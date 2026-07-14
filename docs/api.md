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

- `ContextProvider.load_analysis_context()`: 현재 Thesis와 포트폴리오 Thesis 목록
- `ContextProvider.load_portfolio_theses()`: 자연어 포트폴리오 질의용 전체 Thesis
- `ResearchTools.get_filings()`: SEC/IR/Earnings MCP 조회
- `ResearchTools.get_news()`: News MCP 조회
- `ResearchTools.get_macro()`: Macro MCP 조회

`ResearchRequest`는 기본 Thesis와 `focus_points` 외에 뉴스 최신성 기준인
`lookback_days`(기본 30)와 사전 선별 전 후보 개수인 `candidate_limit`(기본 15)를 제공한다.
백엔드 어댑터는 재검색 라운드별로 다른 `focus_points`를 사용하고, Agent는 반환된
후보를 Source Selector에서 최종 선별한다.

모든 요청·응답 필드명은 `snake_case`를 사용한다. C는 `backend/mcp_tools/` 이외의 외부 데이터 API를
직접 호출하지 않는다.
