# 근거 History 자동 저장 API

> **상태: 구현 완료(B), 프론트 연동 전.** 아래 4개 엔드포인트와 기존 엔드포인트의 `saved_to_history`
> 필드는 이미 백엔드에 구현·테스트돼 있다(`backend/tests/test_analysis.py`). 프론트(A)가 아직 이
> 기능을 붙이지 않았고, 어떤 라우팅/화면 구조로 종목별 History를 보여줄지도 정해지지 않았다 — 이 문서는
> A가 그 결정을 내리고 연결 작업을 할 때 참고할 계약 문서다. 필드가 바뀌면 이 문서와
> `frontend/types/schema.ts`를 같이 갱신한다.

## 배경

기존에는 "주요 근거로 저장"이 프론트 `localStorage`에만 쌓이는 기능이었다(백엔드 연동 없음). 이제는
**재분석(수동 `POST /analyze` 든, 스케줄러의 자동 재분석이든) 결과 근거의 `impact`가 `HIGH` 또는
`MEDIUM`이면 백엔드가 자동으로 History에 저장한다** — 사용자가 버튼을 누를 필요가 없다. `LOW` impact
근거는 자동 저장되지 않고, 필요하면 수동으로 저장/해제할 수 있다.

## 개요

| 항목 | 내용 |
|---|---|
| 자동 저장 규칙 | `evidence.impact in {HIGH, MEDIUM}` → 분석 시점에 자동으로 `saved_to_history=true` |
| 자동 저장이 걸리는 시점 | 수동 재분석(`POST /api/holdings/{id}/analyze`), 스케줄러 자동 재분석 — 둘 다 동일한 백엔드 함수를 공유하므로 한 곳에서 처리됨 |
| 수동 저장/해제 | `LOW` impact 근거를 사용자가 직접 저장하고 싶을 때, 또는 자동 저장된 걸 History에서 빼고 싶을 때 |
| 중복 저장 방지 | 이미 `saved_to_history=true`인 근거는 프론트에서 저장 버튼을 비활성화하면 된다 (아래 "프론트 반영 필요 사항" 참고) |

## 1. `GET /api/portfolios/{portfolio_id}/evidence-history`

포트폴리오에 속한 모든 종목의 저장된 근거를 **종목별로 그룹핑**해서 반환한다. 탭/아코디언/카드 등
어떤 화면 구조를 택하든 한 번의 요청으로 다 가져올 수 있게 하기 위함이다.

```http
GET /api/portfolios/{portfolio_id}/evidence-history
Authorization: Bearer {token}
```

### 응답

```ts
type EvidenceHistoryResponse = EvidenceHistoryGroup[];

interface EvidenceHistoryGroup {
  holding_id: string;
  ticker: string;
  entries: Evidence[];   // 이 종목의 저장된 근거, 최신순
}
```

- 저장된 근거가 하나도 없는 종목은 배열에 아예 등장하지 않는다(빈 `entries: []` 그룹을 만들지 않음).
- 그룹 순서는 **각 종목의 가장 최근 저장 근거 시각** 기준 내림차순이다.
- 그룹 안 `entries`도 최신순(내림차순)이다.

### 예시 응답

```json
[
  {
    "holding_id": "467c2788-65b0-4265-b1be-9420da77f518",
    "ticker": "NVDA",
    "entries": [
      {
        "id": "e1...",
        "thesis_id": "7a6cb256-3f02-4210-982f-187c7018197a",
        "document_id": "0001045810-26-000060",
        "source_type": "SEC_FILING",
        "source_url": "https://www.sec.gov/Archives/edgar/data/...",
        "vector_doc_id": null,
        "content_snippet": "...",
        "classification": "SUPPORT",
        "impact": "HIGH",
        "reason": "...",
        "related_assumptions": ["하이퍼스케일러의 AI capex가 지속 성장한다"],
        "evidence_scope": "NEW",
        "published_at": "2026-06-24T00:00:00Z",
        "saved_to_history": true,
        "created_at": "2026-07-14T05:10:02Z"
      }
    ]
  },
  {
    "holding_id": "9c1a...",
    "ticker": "AAPL",
    "entries": [ "..." ]
  }
]
```

## 2. `GET /api/holdings/{holding_id}/evidence-history`

동일한 데이터를 종목 하나로만 스코프한 버전. 프론트가 종목 상세 페이지/라우팅 방식으로 History를
보여주기로 하면(포트폴리오 전체를 한 번에 안 받고 종목별로 lazy하게 받고 싶을 때) 이걸 쓴다.

```http
GET /api/holdings/{holding_id}/evidence-history
Authorization: Bearer {token}
```

### 응답

```ts
type HoldingEvidenceHistoryResponse = Evidence[];  // 최신순, ticker/holding_id 없음(이미 알고 있으므로)
```

- 종목에 아직 등록된 투자 논리(Thesis)가 없으면 `200` + `[]` (에러 아님).
- 저장된 근거가 없어도 `200` + `[]`.

## 3. `POST /api/evidence/{evidence_id}/save`

특정 근거를 수동으로 History에 저장한다(주로 자동 저장 대상이 아닌 `LOW` impact 근거용). 이미
`saved_to_history=true`인 근거에 다시 호출해도 그냥 `true`로 유지되며 에러 나지 않는다(idempotent).

```http
POST /api/evidence/{evidence_id}/save
Authorization: Bearer {token}
```

응답: `Evidence`(변경된 `saved_to_history: true` 포함) — 200.

## 4. `DELETE /api/evidence/{evidence_id}/save`

History에서 제거한다(자동 저장된 것도, 수동 저장된 것도 동일하게 동작). 기존 "History에서 삭제"
버튼이 이걸 호출하면 된다.

```http
DELETE /api/evidence/{evidence_id}/save
Authorization: Bearer {token}
```

응답: 본문 없음 — `204`.

> 주의: 이 삭제는 **`Evidence` 행 자체를 지우는 게 아니라 `saved_to_history`만 `false`로 되돌리는
> 것**이다. 근거 데이터 자체(분석 결과의 일부)는 그대로 남아 있고, "History 화면에서만" 안 보이게
> 된다.

## 기존 엔드포인트 변경 사항

`Evidence`가 나오는 **모든** 기존 응답에 `saved_to_history: boolean` 필드가 추가됐다 — 새 엔드포인트를
안 붙이더라도 이미 내려가고 있다.

- `POST /api/holdings/{id}/analyze`의 `evidence[]`
- `GET /api/holdings/{id}/analysis`의 `evidence[]`
- `POST /api/portfolios/{id}/query`는 해당 없음(응답에 근거 원문을 안 돌려줌)

즉 종목 상세/분석 화면에서 근거 카드를 렌더링할 때 `evidence.saved_to_history`를 보고 **저장 버튼을
바로 비활성화**할 수 있다 — 굳이 History API를 따로 조회할 필요 없이 그 자리에서 판단 가능하다.

## 프론트 반영 필요 사항 (`frontend/types/schema.ts`)

1. **`Evidence` 인터페이스에 `saved_to_history: boolean` 추가.** 지금은 이 필드가 아예 없어서, 이미
   내려오고 있는 값을 프론트가 못 읽는 상태다.
2. **`EvidenceHistoryGroup` 인터페이스 신규 추가** (위 1번 엔드포인트 응답 타입).
3. 저장 버튼: `evidence.saved_to_history`가 `true`면 비활성화 + "저장됨" 표시, `false`면 클릭 시
   `POST /api/evidence/{id}/save` 호출.
4. History 탭: 기존 `localStorage` 읽기(`SavedEvidenceHistory.tsx`)를 `GET
   /api/portfolios/{id}/evidence-history`(또는 종목별로 갈 경우 2번 엔드포인트) 호출로 교체. "History에서
   삭제" 버튼은 `DELETE /api/evidence/{id}/save` 호출로 교체.

## 에러

| 상황 | 응답 |
|---|---|
| 로그인 안 함 | `401` |
| 본인 소유 포트폴리오/종목/근거가 아니거나 존재하지 않음 | `404` |
| 종목에 아직 투자 논리 없음(2번 엔드포인트) | `200` + `[]` (에러 아님) |

## 구현 참고 (B 담당, 이미 완료)

- `Evidence.saved_to_history` 컬럼: `backend/migrations/versions/0007_evidence_saved_to_history.py`,
  기본값 `false`.
- 자동 저장 로직: `backend/src/thesisguard_backend/routers/analysis.py`의
  `_HISTORY_WORTHY_IMPACT = {HIGH, MEDIUM}`, `run_analysis_and_save`에서 evidence row 생성 시 적용.
  수동/자동 재분석이 이 함수를 공유하므로 두 경로 모두 자동 커버됨.
- 라우트 정의: 같은 파일의 `get_evidence_history`(포트폴리오·그룹핑), `get_holding_evidence_history`
  (종목 단일), `save_evidence`/`unsave_evidence`(수동 토글).
- 스키마: `backend/src/thesisguard_backend/schemas.py`의 `EvidenceResponse.saved_to_history`,
  `EvidenceHistoryGroupResponse`.
- 테스트: `backend/tests/test_analysis.py` (그룹핑, 자동/수동 저장, 소유권 검증, 논리 없는 종목의 빈
  응답 케이스).
