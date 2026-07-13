# ThesisGuard

LLM 기반 개인 투자 포트폴리오 및 투자 논리 모니터링 시스템. 3인 팀(A: Frontend, B: Backend & Data Infra, C: AI/Agent Core)이 개발한다.

## 먼저 확인할 문서

작업을 시작하기 전에 아래 문서를 우선 참고한다.

- **`ThesisGuard_Team_Guide.md`** — 역할 분담, DB 스키마, API 계약, Enum 정의, 협업 규칙을 담은 팀 전체 레퍼런스.
- **`docs/api.md`, `docs/schema.md`** — C가 정리한 B↔C 함수 계약과 Enum·필드 스키마. **`agents/` 코드가 실제로
  바뀌면 이 두 문서와 `agents/__init__.py`가 가장 최신 소스다.**
- **`backend/README.md`** — B가 실제로 무엇을 구현했는지, 설치·실행 방법, 알려진 한계.
- **`ThesisGuard_Project_Proposal.pdf`** — 최초 프로젝트 제안서 (배경/문제정의 확인용, 세부 스펙은 위 문서들이 우선).

## 현재 구현 상태 (2026-07-13 기준)

- **`agents/`** — C 소유, 구현 완료. 이전에는 `src/thesisguard_agent/`였으나 **`agents/`(레포 최상위)로
  구조가 바뀌었다** — `ports.py`→`contracts.py`, `workflow.py`→`graph.py`+`runtime.py`+`state.py`+`nodes/`,
  `llm.py`→`model.py`, `api.py`는 사라지고 `configure_agent()`/`run_analysis_workflow()`/
  `arun_analysis_workflow()`가 `graph.py`에 직접 노출된다. **`structure_thesis`/`answer_portfolio_query`는
  모듈 레벨 함수가 없고 `ThesisGuardAgent` 인스턴스 메서드로만 존재**한다.
- **`backend/`** — B 소유, 구현 완료 + `agents/` 리네임에 맞춰 재동기화 완료. FastAPI 앱, SQLAlchemy
  모델·Alembic 마이그레이션, MCP Tool(SEC/News/Market/Macro), `agents.contracts`의 Protocol을 구현한
  어댑터(`agent_adapters.py`), 인증·포트폴리오·Thesis·분석·알림·자연어질의 REST API, Alert Engine. 실제
  Postgres/LLM API 키로 실행 검증은 아직 안 됨. 설치·실행·한계는 `backend/README.md` 참고.
- **`frontend/`** — A 작업 중. `index.html` + `js/api.js`(mock/live 토글 API 클라이언트). **주의: A의 mock
  스키마는 B의 실제 API와 필드명·ID 체계가 다르다** (아래 참고).

## 알려진 한계 / 미해결 항목

- `backend/README.md`의 "알려진 한계 / TODO" 절 참고 (주간 알림 스케줄러 없음, Vector Store 미연결 등).
- **A↔B 필드 스키마 불일치 (미해결, 팀 논의 필요)**: `frontend/js/api.js`의 mock은 정수 ID, `cash_ratio`/
  `target_weight`를 0~1 비율, `raw_text`/`key_premises` 같은 필드명을 가정한다. 반면 B의 실제 API
  (`backend/src/thesisguard_backend/schemas.py`)는 UUID, 0~100 퍼센트, `raw_input`/`key_assumptions`를
  쓴다. 엔드포인트도 다르다(A는 `/api/theses/{id}/analyze` + `/api/holdings/quick-add`를 가정하지만 B는
  `/api/holdings/{id}/analyze`만 있고 quick-add는 없음). **어느 쪽 스키마로 통일할지는 아직 팀이 정하지
  않았다** — 임의로 한쪽에 맞추지 말고 먼저 논의할 것.
- `backend/app/`, `backend/mcp_tools/`(레포 최상위 빈 `.gitkeep`)와 `backend/src/thesisguard_backend/`
  (실제 코드) 두 레이아웃이 공존한다. 정리 필요.

## 코딩 컨벤션

`ThesisGuard_Team_Guide.md`의 "협업 규칙" 절(Git 브랜치 전략, 커밋 컨벤션, Python/TS/DB/API 네이밍, black/ruff·eslint/prettier)을 그대로 따른다.
