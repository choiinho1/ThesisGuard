# ThesisGuard Backend & Data Infra

이 디렉터리는 3인 팀 중 **B(Backend & Data Infra)**가 소유하는 코드다. `../agents`(C 소유)를
호출해 분석을 실행하고, 결과를 PostgreSQL에 저장하며, A(Frontend)가 쓸 REST API를 제공한다.

## 담당 경계

- **A(Frontend)**: 이 API만 호출한다. `agents`나 `thesisguard_backend`를 직접 import하지 않는다.
- **B(Backend, 이 폴더)**: 인증, DB, REST API, MCP Tool(SEC/News/Market/Macro), 결과 저장, 이메일 발송.
- **C(AI Agent, `../agents`)**: Thesis 구조화, 증거 분류, Bull/Bear/Judge, 집중도 분석, 알림 판정.

C는 `agents/contracts.py`에 `ContextProvider` / `ResearchTools` / `AnalysisModel` Protocol만 정의해두고
절대 DB나 외부 API를 직접 호출하지 않는다. 이 폴더의 `agent_adapters.py`가 그 세 Protocol을 구현해서 앱
시작 시 주입한다(`main.py`의 `lifespan`).

C가 노출하는 진입점은 두 종류다.

- 모듈 레벨(권장): `agents.graph.arun_analysis_workflow()`, `agents.graph.configure_agent()` — FastAPI처럼
  이미 이벤트 루프 안에 있는 async 코드에서 쓴다. **동기 버전 `run_analysis_workflow()`는 이벤트 루프
  안에서 호출하면 `RuntimeError`를 던지도록 막혀 있으니 FastAPI 라우트에서는 쓰지 않는다.**
- 인스턴스 메서드: `astructure_thesis()`, `aanswer_portfolio_query()` 등은 모듈 레벨로 노출되어 있지 않다.
  B가 시작 시 만든 `ThesisGuardAgent` 인스턴스를 `app.state.agent`에 들고 있다가(`deps.get_agent`) 그
  인스턴스에서 직접 호출한다.

## 설치

```powershell
# 1) 저장소 루트에서 C(AI Agent) 패키지(agents/)를 먼저 editable 설치한다
cd ..
python -m pip install -e ".[dev]"

# 2) 이 폴더(backend)에서 백엔드 패키지를 설치한다
cd backend
python -m pip install -e ".[dev,llm-openai]"
```

`llm-openai` extra는 팀이 다른 LLM provider를 쓰기로 하면 `agent_adapters.create_chat_model()`에 분기를
추가하고 그에 맞는 extra로 바꾸면 된다.

## 환경 설정

```powershell
copy .env.example .env
```

`.env`를 채운다. 로컬 개발 중 이메일을 실제로 보내고 싶지 않다면 `EMAIL_DRY_RUN=true`(기본값)를 유지한다 —
발송 대신 로그로만 출력된다.

## DB 준비 & 마이그레이션

PostgreSQL이 필요하다(로컬 설치 또는 Docker). `evidence`/`analysis_results` 등은 pgvector 없이도 동작하며,
RAG용 Vector Store(ADR-0002)는 별도로 붙인다.

```powershell
alembic upgrade head
```

스키마를 바꿀 때는(`models.py` 수정 후) 새 마이그레이션을 생성한다:

```powershell
alembic revision --autogenerate -m "설명"
alembic upgrade head
```

## 실행

```powershell
uvicorn thesisguard_backend.main:app --reload
```

`GET /health`로 살아있는지 확인하고, `/docs`에서 전체 API(OpenAPI)를 바로 확인할 수 있다.

## 빠른 동작 확인 (curl)

```bash
# 회원가입 + 로그인
curl -X POST localhost:8000/api/auth/signup -H "Content-Type: application/json" \
  -d '{"email":"a@a.com","password":"password123","name":"Kim"}'
TOKEN=$(curl -s -X POST localhost:8000/api/auth/login -H "Content-Type: application/json" \
  -d '{"email":"a@a.com","password":"password123"}' | jq -r .access_token)

# 포트폴리오 -> 종목 -> 투자논리 등록
PID=$(curl -s -X POST localhost:8000/api/portfolios -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"name":"AI Growth","cash_ratio":20}' | jq -r .id)
HID=$(curl -s -X POST localhost:8000/api/portfolios/$PID/holdings -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ticker":"NVDA","quantity":10,"avg_buy_price":120,"target_weight":20}' | jq -r .id)
curl -X POST localhost:8000/api/holdings/$HID/thesis -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"raw_input":"NVDA is well positioned as Hyperscaler AI capex keeps growing and demand for its GPUs stays strong."}'

# 분석 실행 (C 워크플로 호출 — OPENAI_API_KEY 필요)
curl -X POST localhost:8000/api/holdings/$HID/analyze -H "Authorization: Bearer $TOKEN"

# 자연어 질의 (evidence는 최신 50건을 그대로 넘김 — 아래 "알려진 한계" 참고)
curl -X POST localhost:8000/api/portfolios/$PID/query -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"question":"내 포트폴리오에서 가장 위험한 종목은?"}'
```

## agents/ 쪽 계약이 바뀌면 항상 확인할 것

C의 `agents/` 패키지는 이미 한 번 구조가 크게 바뀐 적이 있다(모듈 경로, 함수명, 일부 Enum 값). 계약이
또 바뀌면 아래를 순서대로 맞춘다.

1. `agent_adapters.py`의 `from agents...` import들이 실제로 존재하는지
2. `deps.get_agent()` / `main.py` lifespan이 여전히 `agents.graph.configure_agent` 시그니처와 맞는지
3. `models.py`가 재사용하는 Enum(`EvidenceClassification`, `EvidenceImpact`, `EvidenceSourceType`,
   `ThesisStatus`, `AlertSeverity`, `AnalysisType`)이 `agents.models`와 값이 같은지 — 다르면 새
   Alembic 마이그레이션 필요
4. `routers/analysis.py`가 `ThesisAnalysisResult`의 모든 필드(특히 `concentration.common_risks`처럼
   나중에 추가된 필드)를 빠짐없이 저장하는지

## 알려진 한계 / TODO

- **자연어 포트폴리오 질의**(`POST /api/portfolios/{id}/query`)는 이제 C의 `aanswer_portfolio_query()`에
  연결되어 동작한다. 다만 근거로 넘기는 Evidence를 질문과 무관하게 **최근 50건**으로만 뽑는다 — Vector
  Store(ADR-0002)가 아직 없어서 질문과 의미적으로 관련된 근거만 골라내는 검색이 없다.
- **주간 요약 발송**(`alert_engine.send_weekly_digest`)은 함수만 있고 스케줄러가 없다. Windows 작업 스케줄러나
  APScheduler로 주 1회 각 사용자에 대해 호출하도록 팀이 정해야 한다.
- **Vector Store**(ADR-0002, pgvector/Qdrant)는 아직 붙어 있지 않다. 현재 RAG는 SEC EDGAR/뉴스 RSS를
  매 분석 요청마다 실시간으로 조회하는 방식이라 과거 문서 재사용·유사도 검색은 없다.
- **News MCP**: 원래 TDD의 MCP Tool 표에는 없었지만 `ResearchTools.get_news()` 계약을 채우기 위해
  Google News RSS 기반으로 새로 추가했다(`mcp_tools/news.py`).
- `POST /api/portfolios/{id}/rebalance`는 리밸런싱 기록만 남기고, TDD가 언급한 "집중도 변화 분석"은
  자동으로 트리거하지 않는다. 필요하면 리밸런싱 이후 프론트에서 `/analyze`를 각 종목에 대해 호출한다.
- **`backend/app/`, `backend/mcp_tools/`(레포 최상위 빈 `.gitkeep` 폴더)는 이 백엔드가 쓰는 폴더가
  아니다.** 실제 코드는 전부 `backend/src/thesisguard_backend/`(src 레이아웃) 아래에 있다. 두 레이아웃이
  섞여 있으니 팀에서 하나로 정리하는 걸 권장한다.
- **프론트엔드에 로그인 화면이 아직 없다.** `frontend/lib/apiClient.ts`는 `localStorage`의
  `thesisguard_access_token`을 읽기만 하고, 그 값을 채워주는 로그인 호출은 프론트 어디에도 없다. 이
  백엔드는 모든 API에 JWT 인증을 강제하므로(`deps.get_current_user`), 지금 상태로 `live` 모드를 켜면
  전부 401이 난다. A가 로그인 화면을 추가하거나, 데모용으로 devtools에서 토큰을 수동으로 넣거나 — 팀이
  정할 문제라 백엔드에서 임의로 인증을 풀지 않았다.

## 프론트엔드(A) 스키마 정합성

`frontend/`는 `feature/fe-schema-alignment` 브랜치에서 가져왔다(2026-07-13). `frontend/types/schema.ts`가
API 계약의 기준이며, 이 백엔드의 응답 스키마(`schemas.py`)는 그것과 필드 단위로 맞춰져 있다 —
`PortfolioDashboard`(대시보드)와 `HoldingAnalysisResponse`(`/analyze` 응답)는 프론트 타입 이름과 키
이름(`version`, `analysis_result`, `latest_change` 등)까지 그대로 따른다.

```powershell
# 필드셋 대조 + 실제 LangGraph 실행으로 직렬화까지 검증
PYTHONPATH="..;src" ../.venv/Scripts/python.exe scripts/check_fe_schema_compat.py
```

`frontend/types/schema.ts`가 바뀌면 `check_fe_schema_compat.py`의 `FRONTEND_INTERFACES` 딕셔너리를 그
타입 정의에 맞춰 고치고 다시 실행해서 확인한다.
