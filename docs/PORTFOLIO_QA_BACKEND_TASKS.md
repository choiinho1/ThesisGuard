# Portfolio Q&A — 백엔드 담당 작업

작성 기준일: 2026-07-16  
담당 영역: REST API, 인증·소유권 검증, 근거 조회, 응답 조립, 관측성 및 장애 처리

관련 문서:

- [프론트엔드 담당 작업](./PORTFOLIO_QA_FRONTEND_TASKS.md)
- [에이전트 담당 작업](./PORTFOLIO_QA_AGENT_TASKS.md)
- [에이전트·모델 프롬프트 정리](./AGENT_MODEL_PROMPTS.md)

## 1. 목표

사용자의 질문과 해당 포트폴리오의 Thesis·근거를 에이전트에 안전하게 전달하고, 프론트엔드가 답변의 출처와 한계를 표시할 수 있는 완전한 응답을 제공한다.

백엔드는 다음 책임을 가진다.

```text
인증 및 포트폴리오 소유권 확인
  └─ 질문 검증
      └─ 관련 Thesis·근거 조회
          └─ Agent 호출
              └─ Agent가 선택한 근거 검증
                  └─ 사용자용 API 응답 조립
```

## 2. 현재 백엔드 상태

이미 구현된 항목:

- `POST /api/portfolios/{portfolio_id}/query`
- 질문 길이 `1~500자` 검증
- 포트폴리오 소유권 의존성 사용
- 포트폴리오에 속한 Thesis 로딩
- 최신 Evidence 최대 50개 로딩
- `agent.aanswer_portfolio_query()` 호출
- Langfuse 관측성 컨텍스트 연결
- 응답 필드 `answer`, `evidence_document_ids`, `limitations`

현재 한계:

- 근거를 질문과의 의미적 관련성이 아니라 생성 시각의 최신순으로만 선택한다.
- 응답에 raw `document_id`만 있고 티커, 요약, 원문 URL, 발행일이 없다.
- 모델이 선택한 문서 ID를 DB 레코드와 대조하지만 사용자용 상세 근거로 변환하지 않는다.
- Evidence가 어느 holding·ticker에 속하는지 에이전트 입력에서 명확하지 않다.
- 분석 범위, 사용한 근거 수, 근거 최신 시각 등 UI용 메타데이터가 없다.
- 공급자 오류와 timeout에 대한 Portfolio Q&A 전용 HTTP 오류 계약이 명확하지 않다.

주요 수정 예상 파일:

- `backend/src/thesisguard_backend/routers/analysis.py`
- `backend/src/thesisguard_backend/schemas.py`
- 필요 시 `backend/src/thesisguard_backend/agent_adapters.py`
- `backend/tests/test_analysis.py` 또는 Portfolio Q&A 전용 테스트 파일

## 3. API 계약 확정

### 3.1 요청

MVP 요청은 현재 계약을 유지한다.

```json
{
  "question": "포트폴리오가 공통으로 의존하는 가정은 무엇인가요?"
}
```

검증 규칙:

- 선행·후행 공백 제거
- 공백만 있는 질문 거부
- 최소 1자, 최대 500자
- 종목 코드나 자연어를 특정 언어로 제한하지 않음

### 3.2 권장 응답

프론트엔드가 검증 가능한 근거 카드를 만들 수 있도록 상세 근거를 반환한다.

```json
{
  "answer": "포트폴리오는 AI 인프라 투자 확대 가정에 공통으로 의존합니다.",
  "evidence": [
    {
      "document_id": "sec:NVDA:2026Q2",
      "holding_id": "...",
      "ticker": "NVDA",
      "content_snippet": "...",
      "source_url": "https://...",
      "published_at": "2026-07-10T00:00:00Z",
      "classification": "SUPPORT",
      "impact": "HIGH",
      "related_assumptions": ["..."]
    }
  ],
  "limitations": [
    "최근 저장된 근거 중 질문과 직접 관련된 문서만 검토했습니다."
  ],
  "scope": {
    "holding_count": 7,
    "thesis_count": 7,
    "candidate_evidence_count": 50,
    "selected_evidence_count": 6,
    "latest_evidence_at": "2026-07-15T03:00:00Z"
  }
}
```

권장 Pydantic 모델:

- `NaturalLanguageQueryEvidenceResponse`
- `NaturalLanguageQueryScopeResponse`
- 확장된 `NaturalLanguageQueryResponse`

기존 클라이언트 호환이 필요하면 `evidence_document_ids`를 한 버전 동안 함께 반환할 수 있다. 신규 프론트엔드는 `evidence`를 기준으로 구현한다.

## 4. 필수 구현 작업

### 4.1 포트폴리오 소유권과 데이터 범위 보장

- 요청 사용자가 포트폴리오 소유자인지 기존 `OwnedPortfolio` 의존성으로 확인
- 조회되는 모든 holding, Thesis, Evidence가 해당 포트폴리오에 속하는지 쿼리 조건으로 보장
- 에이전트가 반환한 document ID가 후보 Evidence 목록에 존재하는지 재검증
- 다른 사용자 또는 다른 포트폴리오의 근거가 응답에 섞이지 않도록 테스트

### 4.2 Evidence 조회 시 holding·ticker 포함

Evidence 조회 시 다음 관계를 함께 가져온다.

```text
Evidence → Thesis → Holding → Portfolio
```

필요 데이터:

- Evidence DB ID
- `document_id`
- `holding_id`
- `ticker`
- `content_snippet`
- `source_url`
- `published_at`
- `classification`
- `impact`
- `related_assumptions`
- `created_at`

N+1 쿼리가 생기지 않도록 join 또는 `selectinload`를 사용한다.

### 4.3 질문 관련 근거 선택

단계적으로 구현한다.

#### MVP

- 최근 Evidence 최대 50개 조회
- 중복 `document_id` 제거
- 출처 없는 근거와 지나치게 오래된 근거에 대한 결정론적 한계 문구 추가
- 전체 후보를 에이전트에 전달하되 최대 입력 크기 제한

#### 권장 개선

- 질문을 임베딩하여 Evidence의 `content_snippet`, 관련 가정, 티커와 의미적 유사도 계산
- 질문 관련 상위 근거만 에이전트에 전달
- 종목 하나가 모든 근거 슬롯을 차지하지 않도록 종목별 상한 적용
- 높은 관련성이 없는 경우 이를 `limitations`에 명시

현재 저장 구조에 재사용 가능한 벡터가 없으면 작은 후보 집합에 대한 요청 시점 임베딩 또는 별도 Vector Store 중 하나를 ADR로 결정한다.

### 4.4 에이전트 입력 계약 확장 지원

에이전트가 근거와 종목을 정확하게 연결할 수 있도록 입력 객체에 다음 식별자를 포함하는 방안을 에이전트 담당과 합의한다.

- `holding_id`
- `ticker`
- `thesis_id`

선택지:

1. `EvidenceItem`에 Portfolio Q&A용 선택 필드를 추가
2. 별도 `PortfolioQueryEvidence` 계약 생성
3. 기존 Evidence와 holding 메타데이터를 묶은 Portfolio Q&A context 생성

분석 워크플로 전체에 불필요한 필드가 퍼지는 것을 피하기 위해 별도 Portfolio Q&A context 계약을 권장한다.

### 4.5 모델 선택 근거 검증 및 응답 조립

에이전트가 반환한 `evidence_document_ids`에 대해 다음을 수행한다.

- 후보 목록에 없는 ID 제거
- 중복 ID 제거
- 에이전트가 반환한 순서 유지
- DB 행과 매핑하여 상세 근거 응답 생성
- source URL이 없는 경우 `null` 유지
- 후보가 있었지만 선택된 근거가 없으면 결정론적 한계 추가

raw document ID만 사용자에게 보여주도록 프론트엔드에 책임을 넘기지 않는다.

### 4.6 결정론적 한계 문구 추가

모델이 반환하는 `limitations`와 별개로 백엔드가 사실에 기반한 한계를 추가한다.

예시 조건:

- 포트폴리오에 Thesis가 없는 holding이 있음
- 포트폴리오에 Evidence가 전혀 없음
- 일부 holding에 Evidence가 없음
- 최신 50개 제한으로 전체 근거를 검토하지 못함
- 의미 검색을 사용하지 않고 최신순 후보를 사용함
- 출처 URL 없는 근거가 포함됨
- 근거의 최신성이 기준 기간을 초과함

중복 문구를 제거하고 안정적인 순서로 반환한다.

### 4.7 오류 처리

다음 오류를 구분한다.

| 상황 | 권장 응답 |
|---|---|
| 질문 검증 실패 | `422` |
| 포트폴리오 없음 또는 소유권 없음 | 기존 소유권 정책에 따른 `404` |
| Thesis 없음 | 정상 응답 또는 명시적 `409` 중 제품 정책 확정 필요 |
| 모델 timeout·공급자 장애 | 재시도 가능한 `503` |
| 내부 데이터 계약 오류 | `500`, 내부 로그에 상세 원인 기록 |

모델 오류 메시지나 공급자 API 키 관련 내용을 사용자 응답에 그대로 노출하지 않는다.

### 4.8 관측성과 비용 제어

기존 `observe_llm_operation()`을 유지하고 다음 metadata를 추가한다.

- portfolio ID
- holding 및 Thesis 개수
- 후보 Evidence 개수
- 모델에 전달된 Evidence 개수
- 선택된 Evidence 개수
- 질문 길이
- 검색 방식: `RECENCY` 또는 `SEMANTIC`
- 모델명과 공급자

질문 원문과 근거 본문은 개인정보 및 데이터 정책에 맞는 경우에만 추적 시스템으로 전송한다.

추가 권장 사항:

- 사용자별 간단한 rate limit
- 동일 질문·동일 데이터 버전에 대한 짧은 TTL 캐시 검토
- 입력 근거 개수 및 총 문자 수 상한
- timeout 후 무제한 내부 재시도 금지

## 5. 백엔드에서 하지 않을 일

- 에이전트가 생성한 투자 의견을 매수·매도 신호로 변환하지 않는다.
- Q&A 결과로 Thesis 점수나 상태를 변경하지 않는다.
- 에이전트가 반환한 임의의 URL이나 document ID를 검증 없이 응답하지 않는다.
- 프론트엔드에서 전달한 portfolio ID만 믿고 데이터 범위를 결정하지 않는다.
- raw HTML 근거를 그대로 프롬프트나 응답에 포함하지 않는다.
- API 키, 모델 내부 오류, stack trace를 사용자 응답에 노출하지 않는다.

## 6. 테스트 요구사항

### API 계약

- [ ] 1~500자 질문이 허용된다.
- [ ] 빈 문자열, 공백 문자열, 500자 초과 질문이 거부된다.
- [ ] 응답이 합의된 스키마와 일치한다.

### 권한 및 데이터 격리

- [ ] 다른 사용자의 포트폴리오를 질의할 수 없다.
- [ ] 다른 포트폴리오의 Evidence가 후보나 응답에 포함되지 않는다.
- [ ] 에이전트가 알 수 없는 document ID를 반환해도 응답에서 제거된다.

### 근거 및 한계

- [ ] 반환된 상세 근거가 모두 에이전트가 선택한 ID와 대응한다.
- [ ] 중복 document ID가 한 번만 반환된다.
- [ ] Evidence가 없을 때 정상적인 빈 근거 응답과 한계가 반환된다.
- [ ] 일부 holding에 Thesis 또는 Evidence가 없을 때 한계가 추가된다.

### 장애 처리

- [ ] 모델 timeout이 무한 대기로 이어지지 않는다.
- [ ] 모델 오류가 내부 정보 없이 안정적인 HTTP 오류로 변환된다.
- [ ] 관측성 시스템이 비활성화되어도 API가 정상 동작한다.

## 7. 권장 구현 순서

1. 프론트엔드·에이전트 담당과 요청·응답 계약 확정
2. 상세 Evidence와 scope 응답 스키마 구현
3. Evidence → Thesis → Holding join 및 데이터 격리 테스트
4. 에이전트 선택 ID 검증과 상세 응답 조립
5. 결정론적 limitations 추가
6. timeout·오류 계약과 관측성 보강
7. 의미 기반 Evidence 검색 추가
8. 통합 테스트 및 실제 모델 smoke test

## 8. 완료 조건

- [ ] Portfolio Q&A API가 소유권과 데이터 범위를 강제한다.
- [ ] 프론트엔드가 바로 렌더링 가능한 상세 근거를 반환한다.
- [ ] 근거가 어느 holding·ticker에 속하는지 명확하다.
- [ ] 모델이 생성한 잘못된 document ID가 사용자에게 전달되지 않는다.
- [ ] 데이터 상태에 기반한 한계가 자동으로 추가된다.
- [ ] 모델 장애가 일관된 재시도 가능 오류로 변환된다.
- [ ] 후보·선택 근거 수와 검색 방식이 추적된다.
- [ ] 관련 백엔드 테스트가 통과한다.

