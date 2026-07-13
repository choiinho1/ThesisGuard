# ThesisGuard

LLM 기반 개인 투자 포트폴리오 및 투자 논리 모니터링 시스템. 3인 팀(A: Frontend, B: Backend & Data Infra, C: AI/Agent Core)이 개발한다.

## 먼저 확인할 문서

작업을 시작하기 전에 아래 문서를 우선 참고한다.

- **`ThesisGuard_Team_Guide.md`** — 역할 분담, DB 스키마, API 계약, Enum 정의, 협업 규칙을 담은 팀 전체 레퍼런스.
- **`docs/api.md`, `docs/schema.md`** — C가 정리한 B↔C 함수 계약과 Enum·필드 스키마. **`agents/` 코드가 실제로
  바뀌면 이 두 문서와 `agents/__init__.py`가 가장 최신 소스다.**
- **`frontend/types/schema.ts`** — A가 정리한 API 응답 타입. B의 `schemas.py`가 이것과 필드 단위로 맞춰져
  있다 (`backend/scripts/check_fe_schema_compat.py`로 검증).
- **`backend/README.md`** — B가 실제로 무엇을 구현했는지, 설치·실행 방법, 알려진 한계.
- **`ThesisGuard_Project_Proposal.pdf`** — 최초 프로젝트 제안서 (배경/문제정의 확인용, 세부 스펙은 위 문서들이 우선).

## 현재 구현 상태 (2026-07-13 기준)

- **`agents/`** — C 소유, 구현 완료. 이전에는 `src/thesisguard_agent/`였으나 **`agents/`(레포 최상위)로
  구조가 바뀌었다** — `ports.py`→`contracts.py`, `workflow.py`→`graph.py`+`runtime.py`+`state.py`+`nodes/`,
  `llm.py`→`model.py`, `api.py`는 사라지고 `configure_agent()`/`run_analysis_workflow()`/
  `arun_analysis_workflow()`가 `graph.py`에 직접 노출된다. **`structure_thesis`/`answer_portfolio_query`는
  모듈 레벨 함수가 없고 `ThesisGuardAgent` 인스턴스 메서드로만 존재**한다.
- **`backend/`** — B 소유, 구현 완료. FastAPI 앱, SQLAlchemy 모델·Alembic 마이그레이션, MCP Tool
  (SEC/News/Market/Macro), `agents.contracts`의 Protocol을 구현한 어댑터(`agent_adapters.py`), 인증·
  포트폴리오·Thesis·분석·알림·자연어질의 REST API, Alert Engine. `agents/`와의 호환은
  `backend/scripts/check_agent_compat.py`로, A와의 응답 스키마 호환은 `check_fe_schema_compat.py`로 실제
  실행 검증됨(둘 다 real SEC/News/FRED API 호출 포함, DB/LLM만 fake). 실제 Postgres·실제 LLM(OpenAI 키)
  까지 붙여서 돌린 적은 아직 없음. 설치·실행·한계는 `backend/README.md` 참고.
- **`frontend/`** — A 작업 중, `feature/fe-schema-alignment` 브랜치 기준(Next.js/TypeScript, mock/live 토글
  가능한 대시보드). **로그인 화면이 아직 없어서 `live` 모드는 전부 401이 난다** — `backend/README.md`의
  "알려진 한계" 참고.

## 알려진 한계 / 미해결 항목

`backend/README.md`의 "알려진 한계 / TODO" 절 참고 — 주간 알림 스케줄러 없음, Vector Store 미연결,
프론트 로그인 화면 없음(→ live 모드 401), `backend/app/`·`backend/mcp_tools/`(빈 `.gitkeep`)와
`backend/src/thesisguard_backend/`(실제 코드) 레이아웃 중복 등.

## 코딩 컨벤션

`ThesisGuard_Team_Guide.md`의 "협업 규칙" 절(Git 브랜치 전략, 커밋 컨벤션, Python/TS/DB/API 네이밍, black/ruff·eslint/prettier)을 그대로 따른다.
