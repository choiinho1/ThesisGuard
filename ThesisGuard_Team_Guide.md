# ThesisGuard — 3인 팀 개발 가이드

> "내가 왜 투자했는지를 AI가 기억하고, **그 이유가 아직 유효한지를 새로운 정보가 나올 때마다 검증한다.**"

ThesisGuard는 사용자의 투자 논리(Thesis)를 기억하고, 새로운 공시·뉴스·거시 데이터가 그 논리를 강화하는지 약화시키는지 지속적으로 대조해 설명하는 LLM 기반 투자 리서치 Agent 시스템이다. 이 문서는 3인이 겹치는 작업 없이 병렬로 개발할 수 있도록 **역할 · DB 스키마 · API 계약 · 협업 규칙**을 한 곳에 정리한 팀 레퍼런스다.

**MVP 대표 기능**: ① Thesis Change Detection ② Explainable Alert ③ Thesis Concentration Analysis
**MVP 제외**: 자동매매 · 매수매도 추천 · 초단위 모니터링

담당자 표기: **A = Frontend**, **B = Backend & Data Infra**, **C = AI/Agent Core**

---

## 목차

1. [전체 아키텍처](#1-전체-아키텍처)
2. [역할 분담](#2-역할-분담)
3. [담당자 간 인터페이스](#3-담당자-간-인터페이스)
4. [DB 스키마](#4-db-스키마-postgresql)
5. [Vector Store](#5-vector-store)
6. [LangGraph AnalysisState](#6-langgraph-analysisstate)
7. [API 엔드포인트](#7-api-엔드포인트)
8. [MCP Tool](#8-mcp-tool)
9. [협업 규칙](#9-협업-규칙)
10. [폴더 구조](#10-폴더-구조-모노레포)

---

## 1. 전체 아키텍처

파이프라인의 각 단계 옆 괄호는 담당자다.

```
USER
 ↓
Frontend Dashboard                         (A)
 ↓  REST / JSON
FastAPI Backend                            (B)
 ↓  run_analysis_workflow() 호출
LangGraph Workflow — Request Router         (C)
 ↓
┌──────────────┬──────────────┬──────────────┐
Filing Agent    News Agent      Macro Agent    (C, 내부적으로 B의 MCP Tool 호출)
└──────────────┴──────────────┴──────────────┘
 ↓
Evidence Extractor → Thesis Analyzer        (C)
 ↓
┌──────────────┬──────────────┐
Bull Agent      Bear Agent                   (C)
└──────────────┴──────────────┘
 ↓
Judge Agent → Portfolio Agent               (C)
 ↓  ThesisAnalysisResult 반환
DB 저장 + Alert Engine                       (B)  — theses / evidence / alerts 테이블
 ↓
┌──────────────┬──────────────┐
Dashboard 갱신   Email 알림                   (A) / (B)
└──────────────┴──────────────┘
```

---

## 2. 역할 분담

기술 스택표(Frontend / Backend·DB·VectorDB / LLM·Workflow·Evaluation)를 그대로 3명에게 매핑했다. 겹치는 화면·API·Agent가 없도록 기능 단위로 배타적으로 나눴다.

### A. Frontend & Product
**스택**: React · Next.js · TypeScript

사용자가 실제로 보고 조작하는 모든 화면. B가 제공하는 API 스펙을 계약으로 삼아 목데이터로 먼저 개발할 수 있다.

담당 화면·기능:
- [ ] 회원가입 / 로그인 화면 (B의 Auth API 연동)
- [ ] 포트폴리오 생성 · 이름 · 투자 목적 · 투자 기간 입력 폼, 복수 포트폴리오 전환 UI
- [ ] 종목 추가 · 삭제, 보유 수량 · 평균 매수가 · 현금 비중 · 목표 비중 입력 폼
- [ ] 리밸런싱 UI(변경 전/후 비중 입력) + 변경 히스토리 타임라인
- [ ] 투자 논리 자연어 입력 폼 + C가 구조화한 결과(Main Thesis / 핵심 전제 / 긍정·부정 신호 / 리스크) 표시 및 수정 UI
- [ ] 메인 Dashboard: Portfolio 요약, Allocation 차트, Thesis Status 카드(Confidence 변화 화살표), Recent Changes, Risk, Theme Dependency 카드
- [ ] Thesis History 비교 뷰 — 최초 매수 이유 vs 현재 논리, 시계열 Confidence 그래프
- [ ] 자연어 포트폴리오 질의 챗봇 UI (예: "내 포트폴리오가 AI CAPEX 감소에 얼마나 취약해?")
- [ ] Alert 설정 화면(즉시 알림 / 주간 요약 on-off) 및 Alert 목록함

**산출물**: Next.js 앱 레포, B의 OpenAPI 스펙 기반 API 클라이언트, 컴포넌트 단위 목데이터 스토리

---

### B. Backend & Data Infra
**스택**: FastAPI · PostgreSQL · pgvector/Qdrant · MCP · SMTP

시스템의 뼈대와 데이터 파이프라인. A에게는 API를, C에게는 데이터 조회용 MCP Tool을 제공하는 두 얼굴의 역할이다.

담당 기능:
- [ ] 인증(JWT) 및 사용자 관리 API
- [ ] 포트폴리오 / 보유종목 / 거래(리밸런싱) / Thesis / Evidence / Alert REST API 설계·구현·OpenAPI 문서화
- [ ] PostgreSQL 스키마 설계 및 Alembic 마이그레이션 관리
- [ ] Vector DB(pgvector 또는 Qdrant) 구축 및 SEC 공시·IR·실적자료·뉴스 문서 임베딩 적재 파이프라인
- [ ] MCP Tool 서버 4종 구현 — SEC MCP, Market MCP, Macro MCP, Portfolio MCP (외부 API 연동: SEC EDGAR, 시세 API, FRED 등)
- [ ] C가 만든 `run_analysis_workflow()`를 호출하는 분석 트리거 API, 반환값을 theses / evidence / analysis_results 테이블에 저장
- [ ] Alert Engine — C의 분류 결과(Critical / Major / Minor / No Change)에 따라 즉시 알림 또는 주간 요약 이메일 발송
- [ ] 배포 · 환경변수 · Docker 구성

**산출물**: FastAPI 앱, Alembic 마이그레이션 파일, MCP 서버 모듈, A·C에 공유할 OpenAPI 스펙 문서

---

### C. AI / Agent Core
**스택**: LangChain · LangGraph · LangSmith

이 프로젝트의 두뇌. B의 MCP Tool을 LangChain Tool로 감싸 사용하고, 결과를 정해진 형태로 B에게 돌려준다.

담당 기능:
- [ ] 자연어 투자 논리 자동 구조화 (자유 서술 → Main Thesis / 핵심 전제 / 긍정·부정 신호 / 리스크)
- [ ] LangGraph 메인 워크플로우: Request Router → Research(Filing/News/Macro Agent 병렬) → Evidence Extraction → Evidence Classification → Bull → Bear → Judge → (증거 부족 시 Additional Research 루프) → Thesis Update → Portfolio Analysis → Alert Decision
- [ ] Evidence 분류(SUPPORT / CONTRADICT / NEUTRAL / UNCERTAIN) + Impact 판정 + 분류 근거(Reason) 생성
- [ ] Thesis Status 6단계 판정 및 Confidence 점수 산정 로직
- [ ] 설명형 Thesis Update 생성 — 무엇이 변했는가 / 충돌한 전제 / 종합 판단 / 관찰 포인트
- [ ] Bull vs Bear vs Judge Agentic Debate 프롬프트 및 로직
- [ ] Portfolio Thesis Concentration 분석(의미 기반 공통 전제 탐지) 및 공통 위험 탐지
- [ ] 자연어 포트폴리오 질의 응답 로직
- [ ] LangSmith 평가셋 구축: Evidence Classification Accuracy, Thesis Change Detection Accuracy, Tool Selection Accuracy, Citation Groundedness, Contradiction Detection Accuracy 등

**산출물**: `agents/` 파이썬 패키지, 그래프 진입점 `run_analysis_workflow()`, 프롬프트 문서, LangSmith 평가 리포트

---

## 3. 담당자 간 인터페이스

겹치지 않게 나눠도, 결국 이 두 지점에서 세 사람의 코드가 만난다. 아래 계약만 먼저 합의하면 나머지는 각자 병렬로 진행할 수 있다.

### A ⇄ B : REST API
- A → B: HTTP 요청, JSON body는 **snake_case**로 통일 (파이썬 백엔드와 그대로 매칭, 변환 버그 방지)
- B → A: [API 엔드포인트](#7-api-엔드포인트) 섹션의 응답 스키마 그대로 반환
- 계약 소스는 B가 관리하는 OpenAPI 스펙 — A는 이 스펙 기준으로 목데이터를 만들어 먼저 화면부터 완성

### B ⇄ C : 함수 호출 (2026-07-13 실제 구현에 맞춰 수정 — 아래 "구현 확정" 참고)
- B의 API 라우트 핸들러가 C의 `run_analysis_workflow(portfolio_id, holding_id)`를 직접 import해서 호출
- C는 `ThesisAnalysisResult`(Pydantic) 하나로만 응답 — B는 이 결과를 theses / thesis_versions / evidence / analysis_results / alerts에 나눠 저장
- ~~C는 B가 만든 `mcp_tools/`의 함수를 LangChain `@tool`로 감싸 사용~~ → **실제로는 반대(의존성 역전)**: C가 `ports.py`에 `ContextProvider`/`ResearchTools`/`AnalysisModel` Protocol을 정의해두고, B가 이를 구현한 어댑터(`backend/src/thesisguard_backend/agent_adapters.py`의 `BackendContextProvider`/`BackendResearchTools`)를 만들어 앱 시작 시 `configure_default_agent()`로 주입한다. C 코드는 DB나 외부 API를 절대 직접 호출하지 않는다.

**구현 확정 (2026-07-13)**: 위 계약대로 `backend/`에 FastAPI 백엔드 구현 완료. 상세 실행/설치 방법은 `backend/README.md` 참고.

**`run_analysis_workflow` 시그니처** (C가 구현, B가 호출):

```python
def run_analysis_workflow(portfolio_id: str, holding_id: str) -> ThesisAnalysisResult:
    """
    holding_id 종목에 대해 신규 공시·뉴스·거시 데이터를 수집하고
    기존 Thesis와 대조해 변화 여부를 판단한 뒤 결과를 반환한다.
    B는 이 반환값을 그대로 DB에 저장하면 된다.
    """
```

---

## 4. DB 스키마 (PostgreSQL)

모든 테이블은 **B**가 소유·마이그레이션한다. PK는 UUID, 시각 컬럼은 `created_at` / `updated_at`으로 고정한다.

### 공통 Enum 정의

> Enum이란: DB 컬럼에 아무 문자열이나 들어가면 `"지지"` / `"Support"` / `"support"`처럼 표기가 제각각이 돼서 비교·집계가 깨진다. 그래서 "이 컬럼엔 이 단어들만 들어올 수 있다"고 못박아둔 값 목록이다.

**`evidence_classification`** — 신규 정보 한 건이 기존 투자논리와 어떤 관계인지 C(AI)가 분류한 결과
- `SUPPORT` — 기존 논리를 **뒷받침**하는 정보 (예: "Hyperscaler가 AI 투자를 늘렸다" → 논리 강화)
- `CONTRADICT` — 기존 논리의 전제와 **충돌**하는 정보 (예: "CAPEX 축소 발표" → 논리 약화)
- `NEUTRAL` — 있으나 마나 한, 논리에 **영향 없는** 정보
- `UNCERTAIN` — 좋은지 나쁜지 지금 정보만으론 **판단 불가**한 정보

**`thesis_status`** — 이번 분석으로 Thesis **전체**가 어느 방향·강도로 바뀌었는지 (개별 증거 하나의 판정인 `evidence_classification`을 종합한 결과). 왼쪽일수록 강화, 오른쪽일수록 붕괴:
`STRONGLY_STRENGTHENED`(크게 강화) → `STRENGTHENED`(강화) → `UNCHANGED`(변화 없음) → `WEAKENED`(약화) → `STRONGLY_WEAKENED`(크게 약화) → `BROKEN`(논리 자체가 무너짐)

**`evidence_impact`** — ~~HIGH/MEDIUM/LOW~~ **(수정, 2026-07-13)** 분류(지지/반박 여부)와 별개로 그 증거가 판단에서 차지하는 **비중/무게**. C의 실제 계약(`thesisguard_agent.models.EvidenceItem.impact`)은 3단계 Enum이 아니라 **0.0~1.0 사이의 연속값(float)**이다. DB 컬럼도 이에 맞춰 Enum이 아닌 `FLOAT`로 구현했다.

**`evidence_source_type`** — ~~SEC_FILING/IR/EARNINGS/NEWS/MACRO(5종)~~ **(수정, 2026-07-13)** C의 실제 계약(`thesisguard_agent.models.SourceType`)은 3종뿐이다:
- `FILING` — SEC 공시(10-K, 10-Q, 8-K 등)
- `NEWS` — 뉴스 기사
- `MACRO` — 금리·CPI·고용 등 거시경제 지표

(IR/EARNINGS는 별도 출처로 분리하지 않고 필요 시 `FILING`/`NEWS`로 흡수한다. 실제 DB의 `evidence_source_type` Postgres ENUM도 이 3종으로 만들었다.)

**`alert_severity`** — `thesis_status`가 얼마나 크게 바뀌었는지에 따라 정해지는 이메일 알림 등급
- `CRITICAL` / `MAJOR` — 즉시 이메일 발송
- `MINOR` — 주간 요약에 모아서 발송
- `NONE` — 알림 없음 (변화가 없거나 미미함)

**`transaction_type`** — `transactions` 테이블에 기록되는 포트폴리오 변경의 종류
- `BUY` / `SELL` — 매수 / 매도
- `REBALANCE` — 여러 종목 비중을 한 번에 조정
- `CASH_ADJUST` — 현금 비중만 변경

**`analysis_type`** — `analysis_results` 테이블 한 행이 어떤 분석 결과인지 구분하는 태그 (종목 단위 분석과 포트폴리오 단위 분석이 같은 테이블에 저장되기 때문)
- `BULL_BEAR_JUDGE` — 특정 종목 하나에 대한 Bull vs Bear 논쟁 결과 (`thesis_id` 채워짐)
- `THESIS_CONCENTRATION` — 포트폴리오 전체가 특정 테마에 쏠린 정도 (`portfolio_id` 채워짐)
- `COMMON_RISK` — 여러 종목이 동시에 노출된 공통 위험 (`portfolio_id` 채워짐)

| Enum | 값 (요약) |
|---|---|
| `evidence_classification` | `SUPPORT` · `CONTRADICT` · `NEUTRAL` · `UNCERTAIN` |
| `thesis_status` | `STRONGLY_STRENGTHENED` → `STRENGTHENED` → `UNCHANGED` → `WEAKENED` → `STRONGLY_WEAKENED` → `BROKEN` |
| `evidence_impact` | `HIGH` · `MEDIUM` · `LOW` |
| `evidence_source_type` | `SEC_FILING` · `IR` · `EARNINGS` · `NEWS` · `MACRO` |
| `alert_severity` | `CRITICAL` · `MAJOR` · `MINOR` · `NONE` |
| `transaction_type` | `BUY` · `SELL` · `REBALANCE` · `CASH_ADJUST` |
| `analysis_type` | `BULL_BEAR_JUDGE` · `THESIS_CONCENTRATION` · `COMMON_RISK` |

### `users` — 계정

| 필드 | 타입 | 설명 |
|---|---|---|
| id | UUID PK | 사용자 고유 ID |
| email | VARCHAR UNIQUE | 로그인 이메일 |
| password_hash | VARCHAR | 해시된 비밀번호 |
| name | VARCHAR | 표시 이름 |
| created_at / updated_at | TIMESTAMPTZ | 생성·수정 시각 |

### `portfolios` — 사용자별 복수 포트폴리오

| 필드 | 타입 | 설명 |
|---|---|---|
| id | UUID PK | 포트폴리오 ID |
| user_id | UUID FK → users.id | 소유자 |
| name | VARCHAR | 예: "AI Growth Portfolio" |
| investment_purpose | TEXT | 투자 목적 |
| investment_horizon | VARCHAR | 투자 기간 (예: 장기 / 1~3년) |
| cash_ratio | NUMERIC(5,2) | 현금 비중 % |
| created_at / updated_at | TIMESTAMPTZ | - |

### `holdings` — 보유 종목

| 필드 | 타입 | 설명 |
|---|---|---|
| id | UUID PK | 보유 종목 레코드 ID |
| portfolio_id | UUID FK → portfolios.id | - |
| ticker | VARCHAR(10) | 종목코드 (예: NVDA) |
| company_name | VARCHAR | 기업명 |
| quantity | NUMERIC(18,4) | 보유 수량 |
| avg_buy_price | NUMERIC(18,4) | 평균 매수가 |
| target_weight | NUMERIC(5,2) | 목표 비중 % |
| current_weight | NUMERIC(5,2) | 현재 비중 % (분석 시 갱신) |
| created_at / updated_at | TIMESTAMPTZ | - |

### `transactions` — 리밸런싱·매매 히스토리

| 필드 | 타입 | 설명 |
|---|---|---|
| id | UUID PK | - |
| portfolio_id | UUID FK → portfolios.id | - |
| type | transaction_type | BUY / SELL / REBALANCE / CASH_ADJUST |
| before_snapshot | JSONB | 변경 전 종목별 비중 스냅샷 |
| after_snapshot | JSONB | 변경 후 종목별 비중 스냅샷 |
| note | TEXT | 사용자 메모 |
| created_at | TIMESTAMPTZ | 변경 시각 |

### `theses` — 종목별 현재 투자 논리 (1 holding : 1 thesis)

| 필드 | 타입 | 설명 |
|---|---|---|
| id | UUID PK | - |
| holding_id | UUID FK UNIQUE → holdings.id | - |
| raw_input | TEXT | 사용자가 작성한 자연어 원문 |
| main_thesis | TEXT | C가 구조화한 핵심 논지 |
| key_assumptions | JSONB (string[]) | 핵심 전제 목록 |
| positive_signals | JSONB (string[]) | 긍정 신호 |
| negative_signals | JSONB (string[]) | 부정 신호 |
| key_risks | JSONB (string[]) | 주요 리스크 |
| confidence_score | SMALLINT | 0~100 |
| status | thesis_status | 현재 상태 6단계 |
| created_at / updated_at | TIMESTAMPTZ | - |

### `thesis_versions` — Thesis 시계열 History

| 필드 | 타입 | 설명 |
|---|---|---|
| id | UUID PK | - |
| thesis_id | UUID FK → theses.id | - |
| version_no | INT | 버전 번호 (1부터 증가) |
| confidence_score | SMALLINT | 해당 시점 Confidence |
| status | thesis_status | 해당 시점 상태 |
| change_reason | TEXT | "무엇이 변했는가" |
| conflicting_assumptions | JSONB (string[]) | 충돌한 전제 |
| observation_points | JSONB (string[]) | 앞으로 관찰할 포인트 |
| snapshot | JSONB | 해당 시점 thesis 전체 구조 스냅샷 |
| created_at | TIMESTAMPTZ | 분석(버전 생성) 시점 |

### `evidence` — 신규 정보 근거 (2026-07-13 실제 구현에 맞춰 수정)

| 필드 | 타입 | 설명 |
|---|---|---|
| id | UUID PK | - |
| thesis_id | UUID FK → theses.id | - |
| document_id | VARCHAR | C가 부여한 원문 문서 ID (`SourceDocument.document_id`) |
| source_type | evidence_source_type | **FILING / NEWS / MACRO** (3종 — 위 Enum 정의 수정 참고) |
| source_url | TEXT | 원문 링크 |
| vector_doc_id | VARCHAR (nullable) | Vector Store 문서 참조 ID (아직 Vector Store 미연결) |
| content_snippet | TEXT | 근거 원문 발췌 |
| classification | evidence_classification | SUPPORT / CONTRADICT / NEUTRAL / UNCERTAIN |
| impact | **FLOAT (0~1)** | ~~HIGH/MEDIUM/LOW~~ → 연속값으로 수정 (위 Enum 정의 참고) |
| reason | TEXT | 분류 근거 설명 |
| related_assumptions | **JSONB (string[]) — 신규 추가** | 이 근거가 관련된 핵심 전제 목록 (`EvidenceItem.related_assumptions`) |
| published_at | TIMESTAMPTZ (nullable) | 원문 발행일 |
| created_at | TIMESTAMPTZ | 수집·분석 시각 |

### `analysis_results` — Bull/Bear/Judge · Concentration · 공통위험 결과

| 필드 | 타입 | 설명 |
|---|---|---|
| id | UUID PK | - |
| portfolio_id | UUID FK (nullable) | 포트폴리오 단위 분석일 때 |
| thesis_id | UUID FK (nullable) | 종목 단위 분석일 때 |
| analysis_type | analysis_type | BULL_BEAR_JUDGE / THESIS_CONCENTRATION / COMMON_RISK |
| bull_summary | TEXT (nullable) | Bull Agent 요약 |
| bear_summary | TEXT (nullable) | Bear Agent 요약 |
| judge_summary | TEXT (nullable) | Judge 종합 판단 |
| concentration_theme | VARCHAR (nullable) | 예: "AI CAPEX Growth" |
| concentration_score | NUMERIC(5,2) (nullable) | 테마 의존도 % |
| affected_holdings | JSONB (nullable) | 관련 종목 리스트 |
| raw_result | JSONB | LangGraph 원본 결과 전체 (향후 필드 확장 대비) |
| created_at | TIMESTAMPTZ | - |

### `alerts` — 이메일 알림 (2026-07-13: `delivery` 컬럼 추가)

| 필드 | 타입 | 설명 |
|---|---|---|
| id | UUID PK | - |
| user_id | UUID FK → users.id | - |
| portfolio_id | UUID FK → portfolios.id | - |
| thesis_id | UUID FK (nullable) → theses.id | - |
| severity | alert_severity | CRITICAL / MAJOR / MINOR / NONE |
| delivery | **alert_delivery — 신규 추가** | IMMEDIATE / WEEKLY / NONE (`AlertDecision.delivery`를 그대로 저장) |
| title | VARCHAR | 알림 제목 |
| message | TEXT | 알림 본문 |
| is_sent | BOOLEAN default false | 발송 여부 |
| sent_at | TIMESTAMPTZ (nullable) | 발송 시각 |
| created_at | TIMESTAMPTZ | 생성 시각 |

### `alert_settings` — 사용자별 알림 수신 설정 (2026-07-13 신규 추가)

원래 계획에는 없었지만, "즉시 알림 / 주간 요약 설정" API(`GET/PUT /api/users/me/alert-settings`)를 저장할 곳이 필요해 추가했다.

| 필드 | 타입 | 설명 |
|---|---|---|
| user_id | UUID PK, FK → users.id | 사용자당 1행 |
| immediate_alerts_enabled | BOOLEAN default true | CRITICAL/MAJOR 즉시 알림 수신 여부 |
| weekly_digest_enabled | BOOLEAN default true | MINOR 주간 요약 수신 여부 |
| updated_at | TIMESTAMPTZ | - |

---

## 5. Vector Store

pgvector 또는 Qdrant. B가 적재 파이프라인을 구축하고, C의 RAG(Filing/News Agent)가 조회한다. `sec_filings` · `ir_documents` · `earnings_materials` · `news_documents` 4개 컬렉션 모두 동일한 필드 구조를 쓴다.

| 필드 | 타입 | 설명 |
|---|---|---|
| id | VARCHAR PK | 문서 청크 ID |
| ticker | VARCHAR (nullable) | 관련 종목코드 (거시 뉴스는 null) |
| doc_meta | JSONB | filing_type(10-K 등) / doc_title / quarter / headline 등 컬렉션별 메타 |
| published_at | TIMESTAMPTZ | 원문 발행일 |
| chunk_text | TEXT | 청크 원문 |
| embedding | VECTOR(N) | 임베딩 벡터 |
| source_url | TEXT | 원문 링크 |

---

## 6. LangGraph AnalysisState

C 내부에서 그래프 노드 사이를 흐르는 상태. B가 직접 다룰 일은 없지만, C가 무엇을 반환하는지 파악하는 데 참고한다.

```python
class AnalysisState(TypedDict):
    portfolio_id: str
    holding_id: str
    ticker: str
    thesis_snapshot: dict            # 분석 시작 시점의 theses 레코드

    research_data: dict              # {"filings": [...], "news": [...], "macro": [...]}
    evidence_list: list[EvidenceItem]

    bull_report: str
    bear_report: str
    judge_report: str

    updated_confidence: int          # 0~100
    updated_status: str              # thesis_status 값
    change_reason: str
    conflicting_assumptions: list[str]
    observation_points: list[str]

    alert_decision: dict             # {"severity": "MAJOR", "should_send": true}
```

---

## 7. API 엔드포인트

A↔B 계약. Request/Response body는 모두 snake_case.

### Auth

| Method / Path | 설명 |
|---|---|
| `POST /api/auth/signup` | 회원가입 |
| `POST /api/auth/login` | 로그인, JWT 발급 |
| `GET /api/auth/me` | 내 정보 조회 |

### Portfolio

| Method / Path | 설명 |
|---|---|
| `GET /api/portfolios` | 내 포트폴리오 목록 |
| `POST /api/portfolios` | 포트폴리오 생성 |
| `GET /api/portfolios/{id}` | 단건 조회 |
| `PUT /api/portfolios/{id}` | 수정 |
| `DELETE /api/portfolios/{id}` | 삭제 |
| `GET /api/portfolios/{id}/dashboard` | Allocation·Thesis Status·Risk·Theme Dependency 집계 |

### Holdings & Rebalance

| Method / Path | 설명 |
|---|---|
| `POST /api/portfolios/{id}/holdings` | 종목 추가 |
| `PUT /api/holdings/{id}` | 수량·비중 수정 |
| `DELETE /api/holdings/{id}` | 종목 삭제 |
| `POST /api/portfolios/{id}/rebalance` | 리밸런싱 기록 + 테마 집중도 변화 분석 트리거 |

### Thesis & Analysis

| Method / Path | 설명 |
|---|---|
| `POST /api/holdings/{id}/thesis` | 자연어 투자 논리 등록 → C 구조화 트리거 |
| `GET /api/theses/{id}` | 현재 Thesis 조회 |
| `PUT /api/theses/{id}` | 사용자 직접 수정 |
| `GET /api/theses/{id}/history` | thesis_versions 시계열 |
| `POST /api/holdings/{id}/analyze` | 신규 정보 분석 파이프라인 실행 (C 워크플로우 호출) |
| `GET /api/portfolios/{id}/concentration` | Thesis Concentration 결과 |
| `GET /api/portfolios/{id}/common-risk` | 공통 위험 결과 |
| `POST /api/portfolios/{id}/query` | 자연어 질의 |

### Alerts

| Method / Path | 설명 |
|---|---|
| `GET /api/alerts` | 알림 목록 |
| `PATCH /api/alerts/{id}/read` | 읽음 처리 |
| `GET/PUT /api/users/me/alert-settings` | 즉시 알림 / 주간 요약 설정 |

---

## 8. MCP Tool

B가 서버로 구현하고, C가 LangChain Tool로 감싸 Agent에서 호출한다.

| Tool | 함수 | 설명 |
|---|---|---|
| SEC MCP | `get_filings()` · `search_filing()` · `get_company_facts()` | 공시 원문 조회 / 검색 / 재무 팩트 |
| Market MCP | `get_price()` · `get_price_history()` · `get_market_data()` | 현재가 / 시계열 / 시장 데이터 |
| Macro MCP | `get_interest_rate()` · `get_treasury_yield()` · `get_cpi()` | 금리 / 국채금리 / 물가 |
| Portfolio MCP | `get_portfolio()` · `update_portfolio()` · `save_thesis()` · `get_thesis_history()` | DB 레이어 래핑 |

---

## 9. 협업 규칙

세 사람이 같은 코드베이스를 오래 건드릴 수 있도록 정한 최소 규칙. 예외가 필요하면 팀 채널에 먼저 공지한다.

### Git & 리뷰

1. **브랜치 전략** — `main`(배포, 보호) → `dev`(통합) → `feature/{역할}-{기능}` (예: `feature/fe-dashboard`, `feature/be-portfolio-api`, `feature/ai-evidence-classifier`)
2. **커밋 메시지** — Conventional Commits: `feat:` `fix:` `refactor:` `docs:` `chore:` `test:` 접두사를 붙인다.
3. **PR 규칙** — 본인 코드는 셀프 머지 금지, 나머지 2명 중 최소 1명 승인 후 머지. `dev → main`은 데모 전 등 정해진 시점에만.

### 네이밍 컨벤션

4. **Python (B, C)** — PEP8. 변수/함수는 `snake_case`, 클래스는 `PascalCase`, 상수는 `UPPER_SNAKE_CASE`, 파일명은 `snake_case.py`
5. **TypeScript / React (A)** — 변수/함수는 `camelCase`, 컴포넌트·타입은 `PascalCase`. 파일명은 컴포넌트만 `PascalCase.tsx`, 나머지는 `camelCase.ts`
6. **DB / API** — 테이블명은 `snake_case` 복수형, 컬럼명 `snake_case`, PK는 항상 `id`, FK는 `{참조테이블 단수}_id` (예: `user_id`). API 요청·응답 JSON도 동일하게 `snake_case`로 통일해 프론트에서 별도 변환 로직을 두지 않는다.
7. **환경변수** — `UPPER_SNAKE_CASE`. 실제 값은 `.env`(커밋 금지)에, 키 목록만 `.env.example`에 커밋한다.

### 스키마·API 변경

8. **변경 전 공지** — DB 컬럼이나 API 응답 형식을 바꾸기 전 팀 채널에 먼저 알린다. 다른 두 명이 그 필드에 이미 의존하고 있을 수 있다.
9. **마이그레이션 소유** — Alembic 마이그레이션 파일은 B가 관리. 스키마를 바꾸는 PR에는 마이그레이션 파일을 함께 포함한다.

### 코드 품질

10. **포맷터 / 린터** — Python은 `black` + `ruff`, TypeScript는 `eslint` + `prettier`를 커밋 전에 실행한다.
11. **주석** — 무엇을 하는지가 아니라 **왜** 그렇게 했는지만 짧게 남긴다. 이름을 잘 지으면 대부분의 주석은 필요 없다.

### 커뮤니케이션

12. **동기화** — 격일로 짧게 진행상황·블로커 공유. 통합 전에는 각자 목데이터/모킹으로 독립 테스트 후 합친다.

---

## 10. 폴더 구조 (모노레포)

3인이므로 레포 하나에 역할별 최상위 폴더를 나눈다.

```
thesisguard/
├── frontend/          — A
│   ├── app/            (Next.js 라우트)
│   └── components/
├── backend/           — B
│   ├── app/             (FastAPI 라우터, Pydantic 모델)
│   ├── mcp_tools/        (SEC / Market / Macro / Portfolio MCP)
│   └── migrations/       (Alembic)
├── agents/            — C
│   ├── graph.py          (LangGraph 진입점: run_analysis_workflow)
│   ├── nodes/            (Filing/News/Macro/Evidence/Bull/Bear/Judge)
│   └── evaluation/       (LangSmith 평가셋)
└── docs/               (schema.md, api.md — 계약 변경 시 함께 갱신)
```

---

*THESISGUARD — TEAM REFERENCE · A FRONTEND · B BACKEND & DATA · C AI AGENT*
