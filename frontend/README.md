# ThesisGuard Frontend

A(Frontend & Product)가 소유하는 Next.js 영역입니다. 화면과 API 클라이언트 코드는 이 폴더에서 관리합니다.

Next.js App Router와 TypeScript로 구성된 ThesisGuard 프론트엔드입니다.

## 구조

```text
frontend/
├── app/          # Next.js 라우트와 전역 스타일
├── components/   # 화면 컴포넌트
├── lib/          # API 클라이언트와 목데이터
└── types/        # 팀 가이드 DB/API 스키마 타입
```

API 요청·응답 필드는 백엔드 계약과 동일한 `snake_case`를 유지합니다. 기본 모드는 `mock`이며 화면 우측 상단에서 `live`로 전환할 수 있습니다.

## 실행

```powershell
pnpm install
pnpm dev
```

검증 명령은 `pnpm lint`, `pnpm typecheck`, `pnpm build`입니다.
