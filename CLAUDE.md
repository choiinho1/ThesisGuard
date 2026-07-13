# ThesisGuard

LLM 기반 개인 투자 포트폴리오 및 투자 논리 모니터링 시스템. 3인 팀(A: Frontend, B: Backend & Data Infra, C: AI/Agent Core)이 개발한다.

## 먼저 확인할 문서

작업을 시작하기 전에 아래 문서를 우선 참고한다.

- **`ThesisGuard_Team_Guide.md`** — 역할 분담, DB 스키마, API 계약, Enum 정의, 협업 규칙을 담은 팀 전체 레퍼런스. 이 프로젝트의 1차 소스로 취급한다.
- **`docs/AI_AGENT.md`** — C(AI Agent)가 이미 구현한 코드의 실행 흐름, 담당 경계, B와 연결하는 방법, 가드레일.
- **`ThesisGuard_Project_Proposal.pdf`** — 최초 프로젝트 제안서 (배경/문제정의 확인용, 세부 스펙은 위 문서들이 우선).

## 현재 구현 상태

- `src/thesisguard_agent/` — **C 소유**, 구현 완료. LangGraph 워크플로우(`workflow.py`), 공유 Pydantic 계약(`models.py`), B가 구현해 주입할 포트(`ports.py`: `ContextProvider`, `ResearchTools`, `AnalysisModel`), 안정 진입점(`api.py`: `run_analysis_workflow()`, `structure_thesis()`).
- `backend/` — **B 소유**, 1차 구현 완료(2026-07-13). FastAPI 앱, SQLAlchemy 모델·Alembic 마이그레이션, MCP Tool(SEC/News/Market/Macro), C의 Protocol을 구현한 어댑터(`agent_adapters.py`), 인증·포트폴리오·Thesis·분석·알림 REST API, Alert Engine. 설치·실행은 `backend/README.md` 참고. 실제 Postgres/LLM API 키로 아직 실행 검증은 안 됨 — 팀에서 `.env` 채우고 `alembic upgrade head` 후 확인 필요.
- Frontend(A) — 아직 코드 없음.

## 알려진 한계 (backend/README.md "알려진 한계 / TODO" 참고)

- 자연어 포트폴리오 질의(`/api/portfolios/{id}/query`)는 C의 `thesisguard_agent.api`에 대응 함수가 없어 501 반환.
- 주간 알림 요약 발송 함수(`alert_engine.send_weekly_digest`)는 있지만 스케줄러가 없음 — 팀이 cron/APScheduler로 연결해야 함.
- Vector Store(ADR-0002, pgvector/Qdrant)는 아직 안 붙음 — 현재 RAG는 SEC EDGAR/뉴스 RSS를 매 분석마다 실시간 조회.
- ~~B⇄C 인터페이스 불일치~~ — 해결됨. `backend/agent_adapters.py`가 `ports.py`의 Protocol을 정확히 구현하고 있다.

## 코딩 컨벤션

`ThesisGuard_Team_Guide.md`의 "협업 규칙" 절(Git 브랜치 전략, 커밋 컨벤션, Python/TS/DB/API 네이밍, black/ruff·eslint/prettier)을 그대로 따른다.
