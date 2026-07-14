# ThesisGuard 로컬 작업 지침

- 기준 작업 폴더: `C:\agent_project\ThesisGuard` (OneDrive 경로 사용 금지)
- 프런트 검증: `cd frontend`, `pnpm typecheck`, `pnpm lint`, `pnpm build`
- 전체 Python 검증: 저장소 루트에서 `pytest`
- 뉴스/RSS 텍스트는 반드시 `agents.sanitization.sanitize_source_text`를 거쳐 저장합니다.
- Agent fallback은 반드시 `agents.sanitization.safe_source_snippet`을 사용하며 raw HTML을 직접 자르지 않습니다.
- 근거 UI는 카드 전체를 링크로 만들지 않고 기사 제목 또는 `원문 보기`만 링크합니다.
- 기존 `content_snippet`은 자동 삭제하지 않습니다. 스키마 변경 없이 해당 분석을 재실행하면 정제된 값으로 새 결과가 저장됩니다. 운영 DB 일괄 정리는 별도 백업 후 migration/script로 진행합니다.
- 작업 전후 `git status --short`로 다른 사람의 변경을 확인하고, 관련 없는 수정은 커밋에 포함하지 않습니다.
