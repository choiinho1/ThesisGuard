# ThesisGuard Backend & Data Infra

이 디렉터리는 3인 팀 중 **B(Backend & Data Infra)**가 소유하는 코드다. `../src/thesisguard_agent`(C 소유)를
호출해 분석을 실행하고, 결과를 PostgreSQL에 저장하며, A(Frontend)가 쓸 REST API를 제공한다.

## 담당 경계

- **A(Frontend)**: 이 API만 호출한다. `thesisguard_agent`나 `thesisguard_backend`를 직접 import하지 않는다.
- **B(Backend, 이 폴더)**: 인증, DB, REST API, MCP Tool(SEC/News/Market/Macro), 결과 저장, 이메일 발송.
- **C(AI Agent, `../src/thesisguard_agent`)**: Thesis 구조화, 증거 분류, Bull/Bear/Judge, 집중도 분석, 알림 판정.

C는 `ports.py`에 `ContextProvider` / `ResearchTools` / `AnalysisModel` Protocol만 정의해두고 절대 DB나 외부
API를 직접 호출하지 않는다. 이 폴더의 `agent_adapters.py`가 그 세 Protocol을 구현해서 앱 시작 시 주입한다.

## 설치

```powershell
# 1) 저장소 루트에서 C(AI Agent) 패키지를 먼저 editable 설치한다
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
```

## 알려진 한계 / TODO

- **자연어 포트폴리오 질의**(`POST /api/portfolios/{id}/query`, PRD 5.14)는 C의 `thesisguard_agent.api`에
  아직 대응하는 함수가 없어 501을 반환한다. C가 `answer_portfolio_query()` 같은 진입점을 추가하면 연결한다.
  이런 진입점을 만들 때, 서비스 함수는 반드시 결과를 순수 값으로 반환하고 화면 표시 문자열을 직접 만들지
  않아야 한다 — 포매팅은 항상 A(Frontend)의 책임으로 남긴다.
- **주간 요약 발송**(`alert_engine.send_weekly_digest`)은 함수만 있고 스케줄러가 없다. Windows 작업 스케줄러나
  APScheduler로 주 1회 각 사용자에 대해 호출하도록 팀이 정해야 한다.
- **Vector Store**(ADR-0002, pgvector/Qdrant)는 아직 붙어 있지 않다. 현재 RAG는 SEC EDGAR/뉴스 RSS를
  매 분석 요청마다 실시간으로 조회하는 방식이라 과거 문서 재사용·유사도 검색은 없다.
- **News MCP**: 원래 TDD의 MCP Tool 표에는 없었지만 `ResearchTools.get_news()` 계약을 채우기 위해
  Google News RSS 기반으로 새로 추가했다(`mcp_tools/news.py`).
- `POST /api/portfolios/{id}/rebalance`는 리밸런싱 기록만 남기고, TDD가 언급한 "집중도 변화 분석"은
  자동으로 트리거하지 않는다. 필요하면 리밸런싱 이후 프론트에서 `/analyze`를 각 종목에 대해 호출한다.
