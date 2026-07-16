# Portfolio Q&A — 프론트엔드 담당 작업

작성 기준일: 2026-07-16  
담당 영역: 화면 구성, 사용자 상호작용, API 연동, 클라이언트 상태 및 접근성

관련 문서:

- [백엔드 담당 작업](./PORTFOLIO_QA_BACKEND_TASKS.md)
- [에이전트 담당 작업](./PORTFOLIO_QA_AGENT_TASKS.md)
- [에이전트·모델 프롬프트 정리](./AGENT_MODEL_PROMPTS.md)

## 1. 목표

사용자가 포트폴리오 전체의 Thesis와 근거를 자연어로 질의하고, 답변뿐 아니라 사용된 근거와 답변의 한계를 함께 검증할 수 있는 화면을 제공한다.

일반적인 채팅 UI보다 다음 구조의 **근거 기반 단발성 분석 화면**을 우선 구현한다.

```text
질문 입력
  └─ 답변
      ├─ 사용 근거
      └─ 답변의 한계
```

현재 API는 이전 대화 내용을 전달하지 않으므로, 멀티턴 대화를 이해하는 것처럼 보이는 UI를 만들지 않는다.

## 2. 현재 프론트엔드 상태

- `Dashboard`에는 `Main`, `History` 탭만 존재한다.
- Portfolio Q&A 전용 컴포넌트가 없다.
- `frontend/types/schema.ts`에 Portfolio Q&A 요청·응답 타입이 없다.
- `frontend/lib/apiClient.ts`에 `/api/portfolios/{portfolio_id}/query` 호출 함수가 없다.
- Mock 모드용 Q&A 응답과 동작이 없다.
- 현재 공통 디자인은 어두운 녹색 패널, 민트 강조색, 황색 위험·제한 안내를 사용한다.

주요 수정 예상 파일:

- `frontend/components/Dashboard.tsx`
- 신규 `frontend/components/PortfolioQueryPanel.tsx`
- `frontend/types/schema.ts`
- `frontend/lib/apiClient.ts`
- `frontend/lib/mockData.ts`
- `frontend/app/globals.css`

## 3. 필수 구현 작업

### 3.1 `Q&A` 독립 탭 추가

`Dashboard`의 workspace 탭을 다음과 같이 확장한다.

```text
[ Main ] [ Q&A ] [ History ]
```

작업 항목:

- `activeSection` 타입에 `qa` 추가
- `Q&A` 탭 버튼 추가
- `activeSection === "qa"`일 때 `PortfolioQueryPanel` 렌더링
- 포트폴리오가 바뀌면 Q&A 화면 상태 초기화
- 탭에 `aria-current`와 명확한 접근성 라벨 제공

Q&A는 포트폴리오 전체를 대상으로 하므로 선택된 단일 holding의 하위 UI로 배치하지 않는다.

### 3.2 요청·응답 타입 정의

백엔드와 합의한 최종 계약을 `frontend/types/schema.ts`에 정의한다.

권장 타입:

```ts
export interface PortfolioQueryRequest {
  question: string;
}

export interface PortfolioQueryEvidence {
  document_id: string;
  holding_id: string;
  ticker: string;
  content_snippet: string;
  source_url: string | null;
  published_at: string | null;
  classification: EvidenceClassification;
  impact: EvidenceImpact;
  related_assumptions: string[];
}

export interface PortfolioQueryResponse {
  answer: string;
  evidence: PortfolioQueryEvidence[];
  limitations: string[];
}
```

백엔드가 상세 근거 응답을 제공하기 전까지는 기존 `evidence_document_ids: string[]`와 호환되는 임시 타입을 사용할 수 있다. 다만 raw document ID를 최종 사용자에게 주요 정보로 노출하지 않는다.

### 3.3 API 클라이언트 구현

`frontend/lib/apiClient.ts`에 다음 함수를 추가한다.

```ts
queryPortfolio(
  portfolioId: string,
  question: string,
  mode?: ApiMode,
): Promise<PortfolioQueryResponse>
```

실제 모드:

```http
POST /api/portfolios/{portfolio_id}/query
Content-Type: application/json

{
  "question": "포트폴리오의 공통 위험을 설명해 주세요."
}
```

Mock 모드:

- 최소 3개의 대표 질문에 대한 자연스러운 고정 응답 제공
- 알 수 없는 질문에도 일반적인 fallback 응답 제공
- 근거 있음, 근거 부족, 요청 실패 상태를 각각 확인할 수 있게 구성

### 3.4 질문 입력 컴포넌트

필수 요소:

- 2~3줄 높이의 `textarea`
- 최대 500자 제한과 현재 글자 수
- 질문 제출 버튼
- `Ctrl+Enter` 및 `⌘+Enter` 제출 지원
- 빈 문자열 및 공백만 있는 질문 제출 방지
- 제출 중 입력과 버튼 중복 실행 방지
- “답변은 투자 권고가 아닙니다” 안내

권장 범위 표시:

```text
전체 포트폴리오 · Thesis 7개 · 최근 근거 최대 50개
```

실제 개수를 알 수 없는 값은 추정해서 표시하지 않는다. 백엔드 응답에 분석 범위 메타데이터가 추가되기 전까지는 `전체 포트폴리오`만 표시해도 된다.

### 3.5 추천 질문 제공

초기 빈 화면에 다음과 같은 추천 질문 칩을 제공한다.

- 포트폴리오가 공통으로 의존하는 핵심 가정은 무엇인가요?
- 최근 근거에서 여러 종목에 영향을 주는 위험을 알려주세요.
- 현재 근거가 가장 부족한 Thesis는 무엇인가요?
- 서로 충돌하는 가정을 가진 종목이 있나요?

추천 질문 선택 시 입력창에 채우기만 할지 즉시 제출할지 일관되게 결정한다. 오작동 방지를 위해 **입력창에 채우고 사용자가 제출하는 방식**을 권장한다.

### 3.6 답변 카드

답변 영역에 다음 내용을 표시한다.

- 사용자가 입력한 질문
- 모델의 답변
- 생성 시각
- 답변 복사 버튼
- 투자 권고가 아니라는 고정 안내

긴 답변은 문단과 목록이 읽기 쉽게 표시되어야 한다. 백엔드가 Markdown 안전성을 보장하지 않으므로 초기에는 일반 텍스트로 렌더링하고 줄바꿈만 보존하는 방식을 권장한다.

### 3.7 근거 카드

데스크톱에서는 답변과 근거를 `2fr / 1fr`로 나란히 배치한다. 모바일에서는 근거를 답변 아래에 배치한다.

각 근거 카드에 표시할 정보:

- 티커
- `SUPPORT`, `CONTRADICT`, `NEUTRAL`, `UNCERTAIN`
- `HIGH`, `MEDIUM`, `LOW`
- 근거 요약
- 발행일
- 관련 가정
- 원문 링크

원문 링크가 없으면 버튼을 숨긴다. 출처 URL은 새 탭에서 열고 `rel="noreferrer"`를 지정한다.

근거가 없으면 다음과 같이 명시한다.

```text
이 답변에 직접 연결된 근거 문서가 없습니다.
답변의 한계를 확인해 주세요.
```

### 3.8 한계 표시

`limitations`는 답변 하단에 황색 안내 카드로 표시한다.

- 빈 배열이면 영역을 숨긴다.
- 한 개 이상이면 `답변의 한계` 제목과 목록을 표시한다.
- 오류처럼 붉게 표시하지 않고 주의가 필요한 정보로 표현한다.
- 모델이 반환한 한계와 백엔드가 추가한 결정론적 한계를 구분하지 않고 일관된 목록으로 보여준다.

### 3.9 화면 상태 처리

다음 상태를 모두 구현한다.

| 상태 | 화면 동작 |
|---|---|
| 초기 | 설명, 추천 질문, 분석 범위 표시 |
| 입력 중 | 글자 수와 제출 가능 여부 표시 |
| 요청 중 | 입력 비활성화, 로딩 상태, 중복 요청 방지 |
| 성공 | 답변, 근거, 한계 표시 |
| 근거 없음 | 답변과 한계를 표시하고 빈 근거 상태 제공 |
| 오류 | 오류 메시지와 같은 질문 재시도 버튼 제공 |
| 인증 만료 | 기존 API 클라이언트의 인증 만료 처리 사용 |

현재 API가 streaming을 지원하지 않으므로 토큰이 실시간으로 생성되는 것처럼 위장하지 않는다. `포트폴리오 Thesis와 근거를 검토하고 있습니다…` 형태의 로딩 상태를 사용한다.

### 3.10 질문 기록

MVP에서는 서버에 대화를 저장하지 않는다.

- 현재 브라우저 세션 안에서 최근 질문 결과를 카드 목록으로 유지할 수 있다.
- 페이지 새로고침 후 유지된다고 보장하지 않는다.
- 각 요청은 독립적인 질의임을 UI 문구로 분명히 한다.
- 이전 답변을 이해하는 후속 질문 UI는 멀티턴 API가 추가된 뒤 구현한다.

## 4. 접근성 및 반응형 요구사항

- 모든 입력 요소와 버튼에 명시적인 label 제공
- 로딩 결과 영역에 적절한 `aria-live` 사용
- 오류 영역에 `role="alert"` 사용
- 키보드만으로 추천 질문, 제출, 근거 링크 접근 가능
- 900px 이하에서는 단일 열로 전환
- 640px 이하에서는 답변과 근거 카드 여백 및 글자 크기 조정
- 색상만으로 분류나 영향도를 구분하지 않고 텍스트 라벨 병행
- 로딩 스피너에만 의존하지 않고 상태 문구 표시

## 5. 프론트엔드에서 하지 않을 일

- 점수나 Thesis 상태를 클라이언트에서 계산하지 않는다.
- `evidence_document_ids`에 없는 근거를 답변 근거로 임의 표시하지 않는다.
- 백엔드가 지원하지 않는 종목·기간 필터를 동작하는 것처럼 만들지 않는다.
- 일반 텍스트 모델 응답을 검증 없이 HTML로 삽입하지 않는다.
- 이전 질의 내용을 서버가 알고 있는 것처럼 표현하지 않는다.
- 매수·매도 버튼이나 투자 실행을 유도하는 CTA를 Q&A 답변과 연결하지 않는다.

## 6. 권장 구현 순서

1. 백엔드와 최종 응답 스키마 확정
2. TypeScript 요청·응답 타입 추가
3. 실제 및 Mock API 클라이언트 구현
4. `Q&A` 탭과 `PortfolioQueryPanel` 추가
5. 입력·로딩·오류·성공 상태 구현
6. 상세 근거 카드와 원문 링크 구현
7. 반응형·접근성 보완
8. lint 및 production build 검증

## 7. 완료 조건

- [ ] `Main / Q&A / History` 탭 전환이 정상 동작한다.
- [ ] 1~500자의 질문만 제출할 수 있다.
- [ ] 같은 질문의 중복 요청이 방지된다.
- [ ] 성공 응답에서 답변·근거·한계를 모두 확인할 수 있다.
- [ ] 근거 또는 한계가 없는 경우의 빈 상태가 자연스럽다.
- [ ] 오류 발생 후 같은 질문을 재시도할 수 있다.
- [ ] Mock 모드와 실제 API 모드가 모두 동작한다.
- [ ] 모바일에서 가로 스크롤 없이 사용할 수 있다.
- [ ] 키보드와 스크린 리더가 주요 흐름을 이해할 수 있다.
- [ ] `pnpm lint`와 `pnpm build`가 통과한다.

