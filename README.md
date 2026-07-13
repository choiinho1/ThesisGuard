# ThesisGuard

NVIDIA PBL 팀 프로젝트. 사용자의 투자 논리를 구조화하고 신규 공시, 뉴스, 거시지표를 근거로 논리의
변화를 지속적으로 검증합니다.

## Monorepo

- `frontend/`: A - Next.js 화면과 API 클라이언트
- `backend/`: B - FastAPI, PostgreSQL, MCP Tool, Alembic
- `agents/`: C - LangGraph Agent, 프롬프트, 평가
- `docs/`: 팀 간 스키마 및 API 계약

## Team Guide

역할 분담, DB 스키마, API 계약, 협업 규칙과 모노레포 구조는
[docs/TEAM_GUIDE.md](docs/TEAM_GUIDE.md)를 기준으로 합니다.

## Frontend

Next.js App Router 기반 프론트엔드의 실행 방법과 폴더 구조는
[frontend/README.md](frontend/README.md)에서 확인할 수 있습니다.

## AI Agent Core

AI Agent 구현 구조, 백엔드 연결 계약, 설치 및 테스트 방법은
[docs/AI_AGENT.md](docs/AI_AGENT.md)에서 확인할 수 있습니다.
