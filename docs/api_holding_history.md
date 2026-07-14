# GET /api/holdings/{holding_id}/history

> **상태: 설계 확정, 구현 전.** 백엔드(B)가 아직 라우터를 만들지 않았다 — 이 문서는 A가 화면을 먼저
> mock 데이터로 붙여볼 수 있도록 응답 스키마를 확정해서 공유하는 계약 문서다. 필드가 바뀌면 이 문서와
> `frontend/types/schema.ts`를 같이 갱신한다.

## 목적

종목 하나를 선택했을 때, 그 종목의 투자 논리·근거·평가가 시간이 지나며 어떻게 바뀌었는지 분석 회차별로
보여주는 타임라인 화면용 API다. `POST /analyze`를 부를 때마다(수동이든, 향후 예약 자동분석이든) 새
회차가 하나씩 쌓이는데, 지금은 그 이력을 조회할 방법이 없다 — 이 엔드포인트가 그걸 채운다.

## 요청

```http
GET /api/holdings/{holding_id}/history?limit=30&offset=0
Authorization: Bearer {token}
```

| 파라미터 | 위치 | 타입 | 기본값 | 설명 |
|---|---|---|---|---|
| `holding_id` | path | UUID | - | 조회할 종목 |
| `limit` | query | int | 30 | 최대 몇 개 회차를 가져올지 (최신순) |
| `offset` | query | int | 0 | 페이지네이션 오프셋 |

로그인한 사용자가 소유한 종목이 아니면 `404`(다른 종목 관련 API와 동일한 규칙 — 존재 여부를 노출하지
않는다).

## 응답

```ts
interface HoldingHistoryResponse {
  holding_id: string;
  ticker: string;
  thesis: Thesis;              // 현재(최신) 논리 원문 — 회차마다 안 바뀌므로 한 번만 내려준다
  entries: HistoryEntry[];     // 최신 회차가 먼저 오는 내림차순
  total_count: number;         // 페이지네이션용 전체 회차 수
}

interface HistoryEntry {
  version: ThesisVersion;             // 이 회차의 판단/변화 요약
  analysis_result: AnalysisResult | null;  // 이 회차의 Bull/Bear/Judge (아직 한 번도 없었던 회차는 null)
  evidence: Evidence[];               // 이 회차가 수집한 근거만 (과거 회차 것 섞이지 않음)
  alert: Alert | null;                // 이 회차에서 사용자에게 알림이 발생했다면
}
```

`Thesis`, `ThesisVersion`, `Evidence`, `AnalysisResult`, `Alert`는 전부 **기존에 이미 있는 타입 그대로
재사용**한다(`frontend/types/schema.ts`) — 이 엔드포인트만을 위한 새 evidence/analysis 타입은 없다.

> **`Evidence`에 `document_id: string` 필드가 실제로 내려간다.** 지금 `frontend/types/schema.ts`의
> `Evidence` 인터페이스에는 이 필드가 빠져 있는데(기존 `/analyze` 응답에도 이미 내려가고 있었음),
> 이번에 프론트 타입을 갱신할 때 같이 추가해야 한다.

## 예시 응답

```json
{
  "holding_id": "467c2788-65b0-4265-b1be-9420da77f518",
  "ticker": "NVDA",
  "thesis": {
    "id": "7a6cb256-3f02-4210-982f-187c7018197a",
    "holding_id": "467c2788-65b0-4265-b1be-9420da77f518",
    "raw_input": "NVDA benefits from continued hyperscaler AI capex growth...",
    "main_thesis": "NVDA는 하이퍼스케일러의 지속적인 AI 자본지출 성장으로부터 수혜를 입을 것입니다.",
    "key_assumptions": ["하이퍼스케일러의 AI capex가 지속 성장한다", "GPU 수요가 강하게 유지된다"],
    "positive_signals": [],
    "negative_signals": [],
    "key_risks": [],
    "confidence_score": 55,
    "status": "UNCHANGED",
    "created_at": "2026-07-14T04:34:44Z",
    "updated_at": "2026-07-14T05:10:02Z"
  },
  "entries": [
    {
      "version": {
        "id": "5905bea5-7b89-4dc8-9d19-730f8554868e",
        "thesis_id": "7a6cb256-3f02-4210-982f-187c7018197a",
        "version_no": 2,
        "confidence_score": 55,
        "status": "UNCHANGED",
        "change_reason": "신규 근거가 부족하여 판단을 보류했습니다.",
        "conflicting_assumptions": [],
        "observation_points": ["다음 분기 데이터센터 매출 가이던스 확인 필요"],
        "snapshot": { "...": "이 회차 분석 직전 thesis 상태 (Thesis와 동일한 모양)" },
        "created_at": "2026-07-14T05:10:02Z"
      },
      "analysis_result": {
        "id": "b1c2...",
        "portfolio_id": null,
        "thesis_id": "7a6cb256-3f02-4210-982f-187c7018197a",
        "analysis_type": "BULL_BEAR_JUDGE",
        "bull_summary": "...",
        "bear_summary": "...",
        "judge_summary": "신규 근거가 부족하여 판단을 보류했습니다.",
        "concentration_theme": null,
        "concentration_score": null,
        "affected_holdings": [],
        "raw_result": { "...": "ThesisAnalysisResult 전체 JSON" },
        "created_at": "2026-07-14T05:10:02Z"
      },
      "evidence": [
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
          "published_at": "2026-06-24T00:00:00Z",
          "created_at": "2026-07-14T05:10:02Z"
        }
      ],
      "alert": null
    }
  ],
  "total_count": 2
}
```

## 필드 해석 가이드

- **회차(entry) = 분석 실행 1회.** 판단이 `UNCHANGED`로 나와도(논리가 실제로 안 바뀌어도) 회차 자체는
  매번 새로 생긴다. "진짜 바뀐 시점"만 보고 싶으면 `entries[i].version.status !== "UNCHANGED"`로
  프론트에서 필터링한다.
- **`version.snapshot`은 "이 회차 분석 직전" 상태다.** "분석 후" 상태를 보려면 그 회차 자체의
  `version.confidence_score`/`status`를 보거나, 시간순으로 바로 다음 회차(더 과거 방향)의 `snapshot`을
  본다.
- **`evidence`는 해당 회차에서 새로 수집된 것만 온다.** 과거 회차 근거와 안 섞인다.
- **`analysis_result`가 `null`인 경우**: 데이터 정합성상 정상 흐름에서는 발생하지 않는다(분석 1회 =
  버전 1개 + 결과 1개가 항상 같이 생성됨). 방어적으로만 널가능하게 둔 것.
- `entries`는 **최신이 배열의 앞쪽(index 0)**이다 — 타임라인을 위에서 아래로 그리면 자연스럽게
  최신→과거 순이 된다.

## 에러

| 상황 | 응답 |
|---|---|
| 로그인 안 함 | `401` |
| 본인 소유 종목이 아니거나 존재하지 않음 | `404` |
| 종목은 있지만 투자 논리 자체가 없음 | `404` (`entries: []`가 아니라 404 — 아직 분석 대상이 아니라는 뜻) |
| 논리는 있지만 분석을 한 번도 안 함 | `200` + `entries: []` (히스토리는 없지만 종목/논리 자체는 유효) |

## 구현 시 참고 (B 담당)

- `Evidence.thesis_version_id`, `AnalysisResult.thesis_version_id`로 회차별 조인 (각각
  `0003_evidence_versioning`, `0004_analysis_result_version` 마이그레이션에서 추가됨). 이 두 컬럼이 생기기
  전에 만들어진 과거 데이터는 `NULL`이라 회차 매칭이 안 되니, 히스토리에서 자연스럽게 빠지거나
  "회차 미상"으로 처리한다.
- `GET /api/holdings/{id}/analysis`(가장 최근 회차만 돌려주는, 이미 구현된 엔드포인트)와 응답 모양을
  최대한 맞췄다 — `entries[0]`이 사실상 그 엔드포인트의 응답과 거의 동일한 셰이프다.
