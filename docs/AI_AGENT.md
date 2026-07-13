# ThesisGuard AI Agent Core

이 디렉터리는 3인 팀 중 C(AI/Agent Core)가 소유하는 코드다. PRD의 F-2~F-6, TDD의
`run_analysis_workflow()` 계약, ADR-0001/0003/0004를 구현한다.

## 담당 경계

- A(Frontend): 분석 요청과 결과 표시. AI 패키지를 직접 import하지 않는다.
- B(Backend): 인증, DB, REST API, 외부 데이터 MCP Tool, 결과 저장과 이메일 발송을 담당한다.
- C(AI Agent): Thesis 구조화, 증거 분류, Bull/Bear/Judge, 집중도 분석, 알림 결정을 담당한다.

C 코드는 SEC나 뉴스 API를 직접 호출하지 않는다. B가 `ContextProvider`와 `ResearchTools` 프로토콜을
구현해 주입한다. 덕분에 API 키, DB 세션, 재시도와 캐싱은 B의 소유권 안에 남는다.

## 실행 흐름

```text
load_context
    -> prepare_research
    -> Filing / News / Macro Research (병렬)
    -> Evidence Classification
        -> 근거 부족: Additional Research (최대 1회 재수집)
        -> 근거 충분: Bull / Bear (병렬)
    -> Judge
    -> Portfolio Concentration
    -> Alert Decision
    -> ThesisAnalysisResult
```

LangGraph의 fan-out/fan-in을 사용하므로 세 Research 노드와 Bull/Bear 노드는 실제 병렬 super-step으로
실행된다. `research_data`에는 reducer가 적용되어 병렬 결과가 안전하게 합쳐진다.

## 주요 파일

- `models.py`: A/B/C가 공유할 Pydantic 계약과 enum
- `ports.py`: B가 구현할 MCP/DB 포트와 C가 사용하는 모델 포트
- `llm.py`: 임의의 LangChain `BaseChatModel`을 구조화 출력 Agent로 변환
- `workflow.py`: LangGraph 상태와 전체 분석 흐름
- `policy.py`: ADR-0004의 규칙 기반 Alert 매핑
- `api.py`: B가 호출할 안정적인 함수 진입점

## 설치와 검증

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
ruff check .
```

LLM 제공자 패키지는 팀이 모델을 결정한 뒤 백엔드 환경에 별도로 설치한다. 선택한 Chat Model 인스턴스를
`LangChainAnalysisModel`에 넣으면 나머지 워크플로는 제공자와 무관하게 동작한다.

```python
from thesisguard_agent.llm import LangChainAnalysisModel

chat_model = ...  # 팀이 선택한 LangChain BaseChatModel
analysis_model = LangChainAnalysisModel(chat_model)
```

## B와 연결하는 방법

B는 애플리케이션 시작 시 의존성을 한 번 구성한다. `BackendContextProvider`는 DB에서 기존 Thesis와
포트폴리오 Thesis 목록을 읽고, `BackendResearchTools`는 B가 제공하는 MCP Tool을 호출한다.

```python
from thesisguard_agent.api import configure_default_agent, run_analysis_workflow
from thesisguard_agent.workflow import ThesisGuardAgent

agent = ThesisGuardAgent(
    context_provider=BackendContextProvider(...),
    research_tools=BackendResearchTools(...),
    model=analysis_model,
)
configure_default_agent(agent)

# POST /api/holdings/{holding_id}/analyze 내부
result = await run_analysis_workflow(portfolio_id, holding_id)
payload = result.model_dump(mode="json")  # 그대로 DB 저장/REST 응답 가능
```

`ResearchTools`의 각 메서드는 `ResearchRequest`를 받고 `list[SourceDocument]`를 반환해야 한다. 모든 문서는
`source_url`과 원문 `content`를 포함한다. 한 소스가 예외를 발생시켜도 다른 두 소스로 분석을 계속한다.

## 가드레일

- SUPPORT/CONTRADICT에는 URL과 원문 인용이 반드시 있어야 한다.
- 모델이 반환한 인용문이 원문에 없으면 UNCERTAIN으로 강등한다.
- 방향성 근거가 하나도 없으면 Judge LLM을 호출하지 않고 기존 상태와 Confidence를 유지한다.
- LLM 호출은 1회 재시도하며, Judge가 계속 실패하면 기존 상태와 Confidence를 유지한다.
- 집중도 퍼센트는 모델 출력값을 신뢰하지 않고 실제 보유 비중을 합산해 다시 계산한다.
- 문서 본문은 신뢰하지 않는 데이터로 취급하며, 본문 안의 지시를 따르지 않는다.
- 매수·매도·자동매매 추천을 생성하지 않는다.
- Alert는 LLM 자유 판단이 아니라 격리된 규칙 함수로 결정한다.

## 현재 정책값

- 전체 Research 라운드: 최대 2회(최초 수집 + Additional Research 1회)
- 충분한 방향성 근거: 기본 2건
- LLM 호출: 최대 2회(최초 호출 + 재시도 1회)
- BROKEN: CRITICAL 즉시 알림
- STRONGLY_WEAKENED 또는 2단계 이상 하락: MAJOR 즉시 알림
- WEAKENED: MINOR 주간 요약
- 그 외: 발송하지 않음

이 값들은 기획서의 미확정 항목이므로 `WorkflowConfig`와 `decide_alert()`에 격리했다. 팀 합의 후 이 두
위치와 테스트만 수정하면 된다.
