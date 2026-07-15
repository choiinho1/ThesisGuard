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

LLM provider는 `openai`, `gemini`, `upstage`를 지원한다. Upstage는
`python -m pip install -e ".[dev,llm-upstage]"` 후 `LLM_PROVIDER=upstage`,
`LLM_MODEL=solar-pro3`, `UPSTAGE_API_KEY=...`로 설정한다.

Hybrid RAG 임베딩도 같은 `UPSTAGE_API_KEY`를 사용한다. 채팅 모델은 다른 provider를 사용해도
RAG만 Upstage로 실행할 수 있다.

```dotenv
# backend/.env
UPSTAGE_API_KEY=up_발급받은_키
RAG_ENABLED=true
UPSTAGE_EMBEDDING_MODEL=solar-embedding-1-large
RAG_EMBEDDING_TIMEOUT_SECONDS=20
```

키는 저장소 루트가 아니라 `backend/.env`에 넣고 커밋하지 않는다. 키가 없거나 임베딩 요청이
실패하면 규칙 기반 문서 선별로 자동 대체되어 분석 자체는 계속된다.

## 환경 설정

```powershell
copy .env.example .env
```

`.env`를 채운다. 로컬 개발 중 이메일을 실제로 보내고 싶지 않다면 `EMAIL_DRY_RUN=true`(기본값)를 유지한다 —
발송 대신 로그로만 출력된다.

### Google 로그인(선택)

이메일/비밀번호 회원가입·로그인은 `GOOGLE_CLIENT_ID` 없이도 바로 동작한다. 프론트의 "Google로 계속하기"
버튼까지 쓰려면:

1. [Google Cloud Console](https://console.cloud.google.com/apis/credentials) → 프로젝트 선택(또는 생성) →
   "사용자 인증 정보 만들기" → "OAuth 클라이언트 ID" → 애플리케이션 유형 **웹 애플리케이션**.
2. "승인된 자바스크립트 원본"에 사용하는 프론트 개발 서버 주소를 추가한다:
   `http://localhost:3000` 또는 `http://127.0.0.1:3000`.
3. 발급된 Client ID(`....apps.googleusercontent.com`)를 **두 곳에 동일하게** 넣는다:
   - `backend/.env` → `GOOGLE_CLIENT_ID=...`
   - `frontend/.env.local` → `NEXT_PUBLIC_GOOGLE_CLIENT_ID=...` (Client ID는 프론트에 노출돼도 되는
     공개 값이다; Client Secret은 이 플로우에서 쓰지 않는다)
4. 백엔드를 재시작하면 `POST /api/auth/google`이 ID 토큰의 `aud` 클레임을 이 Client ID로 검증하고,
   해당 이메일의 사용자가 없으면 자동으로 새로 만든다.

`GOOGLE_CLIENT_ID`가 비어 있으면 프론트에서 "Google Client ID를 설정하면 Google 가입을 사용할 수
있습니다"라는 fallback 버튼이 뜨는 게 정상 동작이다(오류 아님) — 위 단계를 거치면 사라진다.

### 근거 히스토리 파일

서버 시작 시와 종목 분석 완료 후 DB의 과거 근거·판단을 종목별 Markdown으로 갱신한다.
기본 위치는 `backend/data/evidence_history/{holding_id}.md`이며 소스 관리에는 포함하지 않는다.
분석 Agent는 이 파일 내용을 종목의 스토리를 이해하는 비점수 문맥으로 전달받는다. 과거 근거는
현재 신뢰도·상태에 이미 반영된 기준점이므로 다시 점수화하지 않는다. 전체 이력의 문서 ID와
정규화한 원문 URL은 분류 전에 제외하고, 제외 문서는 Evidence로 재저장하지 않는다. Markdown
표시 개수 제한과 무관하게 전체 이력을 중복 검사에 사용한다. 저장 위치와 표시할 고유 근거 수는
`EVIDENCE_HISTORY_DIR`, `EVIDENCE_HISTORY_MAX_ITEMS`로 조정할 수 있다.
분석 응답에서는 과거의 실질 판정을 `evidence_scope=PAST`, 이번 분석의 신규 판정을
`evidence_scope=NEW`로 구분한다. PAST 근거의 classification/impact는 원래 값을 유지한다.

## DB 준비 & 마이그레이션

PostgreSQL이 필요하다(로컬 설치 또는 Docker). `evidence`/`analysis_results`와 라이브 Hybrid RAG는
pgvector 없이도 동작한다. 과거 문서 전체를 영구 보관·검색하는 Vector Store(ADR-0002)는 별도로 붙인다.

PostgreSQL 없이 로컬 화면과 인증 흐름을 확인하려면 `backend/.env`에
`DATABASE_URL=sqlite+aiosqlite:///./thesisguard.db`를 사용한다. 이 경우 서버 시작 시 로컬 테이블이
자동 생성된다. 팀·배포 환경에서는 아래와 같이 PostgreSQL과 Alembic 마이그레이션을 사용한다.

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

`GET /health`로 서버와 `rag: enabled|disabled` 상태를 확인하고, `/docs`에서 전체 API(OpenAPI)를
바로 확인할 수 있다.

RAG 검색 성능은 `backend` 디렉터리에서 Upstage 임베딩과 RAGAS 골든셋으로 확인할 수 있다.

```powershell
$env:PYTHONPATH="..;src"
..\.venv\Scripts\python.exe scripts\evaluate_rag.py --fail-below 0.9
```

Context Precision, Context Recall, MRR, nDCG 중 핵심 검색 지표가 기준 미만이면 종료 코드 1을
반환하므로 CI 회귀 게이트로도 사용할 수 있다.

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

# 저장된 마지막 분석 결과 다시 조회 (새로고침/화면 전환 후에도 evidence·judge·changes 복원)
curl localhost:8000/api/holdings/$HID/analysis -H "Authorization: Bearer $TOKEN"

# 자연어 질의 (evidence는 최신 50건을 그대로 넘김 — 아래 "알려진 한계" 참고)
curl -X POST localhost:8000/api/portfolios/$PID/query -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"question":"내 포트폴리오에서 가장 위험한 종목은?"}'

# 종목 현재 시세 (일중 고가/저가, 거래량, 30일 등락률 — Yahoo Finance, 지연 시세)
curl localhost:8000/api/holdings/$HID/market-snapshot -H "Authorization: Bearer $TOKEN"
```

## 분석 결과 재조회 (`GET /api/holdings/{id}/analysis`)

`POST /analyze`의 응답(`HoldingAnalysisResponse`: thesis/version/evidence/analysis_result/alert)은 그
호출 한 번의 응답으로만 프론트에 전달됐다 — 프론트가 그 결과를 로컬 state로만 들고 있어서 화면을
벗어났다 돌아오면 사라지고 다시 분석해야 하는 문제가 있었다. 이 GET 엔드포인트가 DB에 저장된 마지막
분석 결과를 동일한 모양으로 다시 돌려준다.

- **`Evidence.thesis_version_id`**: evidence는 분석할 때마다 계속 쌓이기만 하므로(과거 회차 evidence가
  안 지워짐), 이 컬럼 없이는 "최신 분석의 근거만" 골라낼 방법이 없었다. `/analyze`가 `ThesisVersion`을
  만들 때 그 버전의 evidence에 `thesis_version_id`를 같이 채운다.
- **주의**: `thesis_version.id`의 `default=uuid.uuid4`는 **flush 시점에만** 채워진다. `db.add(thesis_version)`
  직후 곧바로 `.id`를 읽으면 `None`이라 evidence의 `thesis_version_id`가 전부 NULL로 저장되는 버그가
  실제로 있었다 — `db.add()` 다음에 반드시 `await db.flush()`를 먼저 하고 `.id`를 읽을 것
  (`tests/test_analysis.py`가 이 회귀를 커버한다).
- 기존 evidence 행(이 컬럼이 생기기 전 데이터)은 `thesis_version_id`가 NULL로 남아있고 어느 분석
  회차 것인지 복원할 수 없다 — 새로 분석해야 다음부터 정상적으로 연결된다.

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
- **라이브 Hybrid RAG**는 붙어 있다. 규칙 필터가 넓게 고른 후보를 청크화하고, 핵심 가정별
  Multi-query dense retrieval + BM25를 RRF로 합친 뒤 MMR로 중복을 제거한다. 선택 청크의 앞뒤 문맥도
  함께 Evidence Agent에 전달하고 동일 원문 임베딩은 프로세스 메모리에서 재사용한다.
- **영구 Vector Store**(ADR-0002, pgvector/Qdrant)는 아직 붙어 있지 않다. 서버 재시작 뒤에도 과거
  문서와 벡터를 재사용하거나 과거 전체 코퍼스에서 검색하는 기능은 다음 단계다.
- **News MCP**: 원래 TDD의 MCP Tool 표에는 없었지만 `ResearchTools.get_news()` 계약을 채우기 위해
  Bing News RSS 우선·Google News RSS 대체 구조로 추가했다(`mcp_tools/news.py`). 검색 시 SEC 정식
  회사명·티커 기본 검색과 핵심 가정별 검색을 병렬 실행하고, Agent Source Selector가 회사명
  불일치·최소 관련도 미달 결과를 제외한다. 뉴스와 공시는 발행일이 확인된 최근 30일 자료만
  사용하며 날짜 없음·기간 초과·미래 날짜 자료는 다운로드 전에 제외한다. 발행사 본문을 읽을 수
  있으면 관련 문단을 사용하고, 동적 페이지·차단·유료벽에서는 RSS 설명으로 안전하게 대체한다.
- `POST /api/portfolios/{id}/rebalance`는 리밸런싱 기록만 남기고, TDD가 언급한 "집중도 변화 분석"은
  자동으로 트리거하지 않는다. 필요하면 리밸런싱 이후 프론트에서 `/analyze`를 각 종목에 대해 호출한다.
- **`backend/app/`, `backend/mcp_tools/`(레포 최상위 빈 `.gitkeep` 폴더)는 이 백엔드가 쓰는 폴더가
  아니다.** 실제 코드는 전부 `backend/src/thesisguard_backend/`(src 레이아웃) 아래에 있다. 두 레이아웃이
  섞여 있으니 팀에서 하나로 정리하는 걸 권장한다.
- **프론트엔드 로그인 화면**(`frontend/components/AuthGate.tsx`, `main` 브랜치 2026-07-13 기준)이 이제
  있다 — 이메일/비밀번호 로그인·회원가입은 별도 설정 없이 바로 동작한다. Google 로그인 버튼은
  `GOOGLE_CLIENT_ID`/`NEXT_PUBLIC_GOOGLE_CLIENT_ID`를 설정해야 활성화된다(위 "Google 로그인(선택)" 참고).

## 프론트엔드(A) 스키마 정합성

`frontend/`는 `feature/fe-schema-alignment` 브랜치에서 가져왔다(2026-07-13). `frontend/types/schema.ts`가
API 계약의 기준이며, 이 백엔드의 응답 스키마(`schemas.py`)는 그것과 필드 단위로 맞춰져 있다 —
`PortfolioDashboard`(대시보드)와 `HoldingAnalysisResponse`(`/analyze` 응답)는 프론트 타입 이름과 키
이름(`version`, `analysis_result`, `latest_change` 등)까지 그대로 따른다.

대시보드의 `current_weight`는 `보유 수량 × Yahoo 최신 종가`로 평가액을 계산한 뒤 전체
주식 평가액에서 차지하는 비율로 갱신한다. 주가 조회가 실패한 종목은 평균 매수가를 사용하고,
주식 비중 합계는 `100 - cash_ratio`가 되도록 계산한다. 갱신된 값은 DB에도 동기화되어 Agent의
포트폴리오 집중도 분석과 같은 값을 사용한다.

```powershell
# 필드셋 대조 + 실제 LangGraph 실행으로 직렬화까지 검증
PYTHONPATH="..;src" ../.venv/Scripts/python.exe scripts/check_fe_schema_compat.py
```

`frontend/types/schema.ts`가 바뀌면 `check_fe_schema_compat.py`의 `FRONTEND_INTERFACES` 딕셔너리를 그
타입 정의에 맞춰 고치고 다시 실행해서 확인한다.

## Langfuse LLM 디버깅

Langfuse에서 프로젝트를 만든 뒤 프로젝트 키를 `backend/.env`에 넣는다. Secret Key는 채팅에
붙여 넣거나 Git에 커밋하지 않는다.

```dotenv
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_TRACING_ENVIRONMENT=development
LANGFUSE_SAMPLE_RATE=1.0
```

셀프 호스팅한 Langfuse를 사용한다면 `LANGFUSE_BASE_URL`만 해당 인스턴스 주소로 바꾼다.
`backend` 디렉터리에서 연결 상태를 확인할 수 있다.

```powershell
..\.venv\Scripts\python.exe scripts\check_langfuse.py
```

백엔드는 다음 LLM 진입점을 추적한다.

- `thesisguard.structure-thesis`: 자연어 투자 논리 구조화
- `thesisguard.analyze-holding`: 리서치, 근거 분류, Bull/Bear/Judge를 포함한 전체 LangGraph
  노드 트리와 모델 프롬프트/응답, 토큰, 지연시간, 오류
- `thesisguard.portfolio-query`: 포트폴리오 질의와 근거 프롬프트

이메일 대신 내부 사용자 UUID를 `user_id`로 사용하고, 포트폴리오 단위로 Langfuse 세션을
묶는다. 모델 프롬프트에는 사용자가 작성한 투자 논리와 수집된 근거가 포함되므로 적절한 데이터
보존 정책을 사용해야 한다. 트래픽이 많아지면 `LANGFUSE_SAMPLE_RATE`를 `1.0`보다 낮춘다.
`GET /health`에는 키 대신 Langfuse 상태와 RAG의 `enabled`/`disabled` 상태만 표시된다.
