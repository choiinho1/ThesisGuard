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

신규 근거의 모델 출력은 가정별 `SUPPORT`/`CONTRADICT`/`NOT_ADDRESSED`와 원문 구간 번호로
제한한다. API에 저장되는 `relevance_score`와 `impact`는 Agent 코드가 인용 유효성 및 출처
유형의 고정 정책으로 산출한 값이며 모델이 직접 생성한 값이 아니다.

모든 요청·응답 필드명은 `snake_case`를 사용한다. C는 `backend/mcp_tools/` 이외의 외부 데이터 API를
직접 호출하지 않는다.

## 자연어 포트폴리오 질의

Portfolio Q&A는 `ThesisGuardAgent` 인스턴스의 async 또는 sync 메서드를 사용한다.

```python
from agents.models import PortfolioQueryEvidence

answer = await agent.aanswer_portfolio_query(
    portfolio_id,
    question,
    evidence=[
        PortfolioQueryEvidence(
            holding_id=holding_id,
            ticker=ticker,
            thesis_id=thesis_id,
            evidence=evidence_item,
        )
    ],
)
```

시그니처는 다음과 같다.

```python
async def aanswer_portfolio_query(
    portfolio_id: str,
    question: str,
    evidence: list[PortfolioQueryEvidence | EvidenceItem] | None = None,
) -> PortfolioQueryAnswer
```

`answer_portfolio_query()`는 동일 계약의 sync 진입점이다. 질문은 앞뒤 공백을 제거한 뒤 1~500자로
검증한다. 신규 연동은 Evidence가 어느 종목에 속하는지 모델이 명확히 알 수 있도록
`PortfolioQueryEvidence`를 사용한다. 기존 Backend 호환을 위해 `EvidenceItem` 목록도 허용하지만,
이 경우 답변의 `limitations`에 종목별 귀속이 제한된다는 문구가 추가된다.

Portfolio Thesis가 없거나 Evidence가 비어 있으면 채팅 모델을 호출하지 않고 결정론적인 안내와
한계를 반환한다. 모델이 반환한 `evidence_document_ids`는 입력 Evidence에 존재하는 값만 남기고
중복을 제거한다. 이 Q&A 결과는 Thesis 점수, 상태, 포트폴리오 비중 또는 알림 판정을 변경하지 않는다.
