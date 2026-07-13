# ThesisGuard AI Agent Core

`agents/`는 3인 팀 중 C(AI/Agent Core)가 소유한다. 팀 가이드의 F-2~F-6과
`run_analysis_workflow()` B-C 계약을 구현한다.

## 폴더 구조

```text
agents/
├── graph.py              # LangGraph 조립 및 공개 진입점
├── models.py             # B-C Pydantic 결과 계약과 DB enum
├── contracts.py          # B의 Context/MCP 포트, LLM 포트
├── model.py              # LangChain 구조화 출력과 프롬프트
├── runtime.py            # 주입 의존성과 정책 설정
├── state.py              # LangGraph AnalysisState
├── policy.py             # 규칙 기반 Alert 등급
├── nodes/
│   ├── filing_agent.py
│   ├── news_agent.py
│   ├── macro_agent.py
│   ├── evidence.py
│   ├── debate.py
│   ├── portfolio.py
│   └── alert.py
└── evaluation/           # LangSmith 평가 레코드와 지표
```

## 분석 흐름

```text
Request Router
  -> Filing / News / Macro Agent (병렬)
  -> Evidence Classification
     -> 근거 부족: Additional Research 1회
  -> Bull / Bear Agent (병렬)
  -> Judge Agent
  -> Portfolio Concentration + Common Risk
  -> Alert Decision
  -> ThesisAnalysisResult
```

`research_data`는 팀 계약대로 `filings`, `news`, `macro` 키를 가진 dict다. 병렬 노드가 같은
상태를 갱신하므로 `agents/state.py`의 reducer가 세 결과를 합친다.

## 설치와 검증

```powershell
python -m pip install -e ".[dev]"
python -m black --check agents tests
python -m ruff check .
python -m pytest
```

## 백엔드 연결

B는 `backend/mcp_tools/` 함수들을 `ResearchTools` 프로토콜로 감싸고 시작 시 Agent를 구성한다.

```python
from agents.graph import ThesisGuardAgent, configure_agent, run_analysis_workflow
from agents.model import LangChainAnalysisModel

agent = ThesisGuardAgent(
    context_provider=BackendContextProvider(...),
    research_tools=BackendResearchTools(...),
    model=LangChainAnalysisModel(chat_model),
)
configure_agent(agent)

result = run_analysis_workflow(portfolio_id, holding_id)
payload = result.model_dump(mode="json")
```

FastAPI의 async 라우트에서는 이벤트 루프를 막지 않도록 `arun_analysis_workflow()`를 사용한다.

## 안전 정책

- C는 외부 데이터 API를 직접 호출하지 않고 B의 MCP 포트만 사용한다.
- 방향성 Evidence는 `source_url` 또는 `vector_doc_id`가 있어야 한다.
- 원문에서 검증되지 않는 인용은 UNCERTAIN/LOW로 강등한다.
- 방향성 근거가 없거나 Judge가 재시도 후 실패하면 기존 Thesis를 유지한다.
- 집중도 퍼센트는 LLM 값 대신 실제 보유 비중 합계로 다시 계산한다.
- Alert는 LLM이 아니라 `policy.py` 규칙으로 결정한다.
- 매수·매도 및 자동매매 추천을 생성하지 않는다.

세부 스키마는 [schema.md](schema.md), B-C 호출 계약은 [api.md](api.md)를 참고한다.
