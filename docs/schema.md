# AI Agent Schema Contract

DB 테이블과 Alembic은 B가 소유한다. C는 아래 enum과 필드명을 그대로 사용해
`ThesisAnalysisResult`를 반환한다.

| Python enum | DB enum | 값 |
|---|---|---|
| `EvidenceClassification` | `evidence_classification` | `SUPPORT`, `CONTRADICT`, `NEUTRAL`, `UNCERTAIN` |
| `ThesisStatus` | `thesis_status` | `STRONGLY_STRENGTHENED`, `STRENGTHENED`, `UNCHANGED`, `WEAKENED`, `STRONGLY_WEAKENED`, `BROKEN` |
| `EvidenceImpact` | `evidence_impact` | `HIGH`, `MEDIUM`, `LOW` |
| `EvidenceSourceType` | `evidence_source_type` | `SEC_FILING`, `IR`, `EARNINGS`, `NEWS`, `MACRO` |
| `AlertSeverity` | `alert_severity` | `CRITICAL`, `MAJOR`, `MINOR`, `NONE` |
| `AnalysisType` | `analysis_type` | `BULL_BEAR_JUDGE`, `THESIS_CONCENTRATION`, `COMMON_RISK` |

## EvidenceItem

`document_id`, `source_type`, `source_url`, `vector_doc_id`, `content_snippet`, `classification`,
`impact`, `reason`, `published_at`을 제공한다. `content_snippet`은 검증된 원문을 기반으로
생성한 500자 이내의 한국어 설명이다. 핵심 사실과 주요 수치·기간, 투자 논리와의 관계를
2~3문장으로 제공한다. `SUPPORT`와 `CONTRADICT`에는 `source_url` 또는
`vector_doc_id`가 필수다.

## AnalysisState

`agents/state.py`가 팀 가이드의 필드를 정의한다. `research_data`의 형태는 다음과 같다.

```python
{
    "filings": list[SourceDocument],
    "news": list[SourceDocument],
    "macro": list[SourceDocument],
}
```

`selected_documents`는 Source Selector가 생성하는 그래프 내부 후보 목록이다. DB/API에는
노출하지 않는다. 회사별 문서의 `metadata.company_identity`에는 `identifier_scheme`,
`identifier`, `ticker`, `exchanges`, `legal_name`, `aliases`, `industry`, `official_domains`를
저장한다. 뉴스 사전 선별 결과는 `metadata.identity_match`의 `status`, `confidence`, `signals`에
기록하며 `status=MATCH`인 문서만 RAG로 전달한다. 현재 미국 기업은 `SEC_CIK`를 사용하고,
동일 계약에 DART `corp_code` 등 다른 시장 식별 체계를 추가할 수 있다.

모델은 관련도나 영향도를 출력하지 않는다. 가정별 SUPPORT/CONTRADICT가
유효한 원문 구간을 인용하면 Agent가 `relevance_score=1.0`을 부여하고, 그렇지 않으면
`NOT_ADDRESSED`, `relevance_score=0.0`으로 처리한다. 방향성 근거의 `impact`는 출처 유형만으로
결정한다. `SEC_FILING`·`EARNINGS`·`IR`은 HIGH, `NEWS`·`MACRO`는 MEDIUM이며,
비방향성 근거는 LOW다.
`EvidenceModelOutput.assumption_findings`는 각 핵심 가정을 원문 전체와 대조한 내부 판정이다.
각 항목은 가정 원문, SUPPORT/CONTRADICT/NOT_ADDRESSED, 근거 구간 번호만 가진다.
문서 전체 classification도 가정별 판정에서 코드가 도출한다. 모두 지지면 SUPPORT, 모두
반박이면 CONTRADICT, 방향이 섞이면 UNCERTAIN, 방향성 근거가 없으면 NEUTRAL이다.
각 finding의 `source_passage_indices`는 Agent가 미리 번호를 붙인 원문 구간 중 최대 3개를
가리킨다. Agent는 이 번호로 실제 구간을 다시 찾아 `EvidenceAssessment.source_excerpt`에
넣으므로, 모델이 원문을 글자 단위로 재현할 필요가 없다. 표시용 한국어 요약만
`EvidenceItem.content_snippet`에 저장하며 요약 생성 실패는 분류 결과와 분리해서 처리한다.

`evidence_history_summary`는 백엔드가 종목별 Markdown 파일로 물질화한 과거 근거·판단
요약이며 파일 내용 그대로 분류/Bull/Bear/Judge 프롬프트에 전달한다. 이 문맥은 현재
종목의 스토리와 새 정보의 연속성·반전·구체화를 파악하기 위한 용도일 뿐 점수 입력이
아니다. 과거 근거는 현재 Thesis 기준점에 이미 반영된 것으로 취급한다.
`evidence_history_document_ids`와 `evidence_history_source_urls`에 포함된 동일 문서는 Source
Selector가 모델 호출 전에 제외한다. URL 비교 시 추적 파라미터를 제거하며, 제외된 자리는
뒤의 신규 후보로 보충한다. 중복 문서를 NEUTRAL/LOW Evidence로 다시 저장하지 않아 기존의
실질적인 SUPPORT/CONTRADICT 판정이 덮이지 않고 한 정보가 반복 가산되지 않게 한다.

REST `EvidenceResponse.evidence_scope`는 `NEW` 또는 `PAST`다. 과거 근거도 원래 평가된
classification과 impact를 보존하며, 시점 구분은 평가 강도와 독립적이다. 따라서 `PAST`가
자동으로 `NEUTRAL/LOW`를 의미하지 않는다.

그래프 내부용 재시도 횟수, 모델 출력 객체, 포트폴리오 문맥은 추가 필드로만 관리하며 B에 노출하지 않는다.

## PortfolioQueryEvidence

Portfolio Q&A에서 Evidence를 holding과 정확히 연결하기 위한 전용 입력 계약이다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `holding_id` | `str` | Evidence가 속한 보유 종목 ID |
| `ticker` | `str` | 입력 포트폴리오에 존재하는 티커 |
| `thesis_id` | `str \| None` | Backend Thesis ID. 알 수 없으면 `None` |
| `evidence` | `EvidenceItem` | 검증된 근거 객체 |

기존 `EvidenceItem` 직접 입력은 호환 목적으로 허용하지만 신규 Backend 연동은
`PortfolioQueryEvidence`를 사용한다.

## PortfolioQueryAnswer

| 필드 | 타입 | 제약 및 설명 |
|---|---|---|
| `answer` | `str` | 1~4,000자 한국어 답변 |
| `evidence_document_ids` | `list[str]` | 최대 20개. 실제 입력 Evidence ID만 허용 |
| `limitations` | `list[str]` | 최대 8개, 항목별 1~500자 |

Agent는 허용되지 않은 문서 ID와 중복 ID를 제거하고, 한계 문구의 공백·중복을 정규화한다.
직접 연결된 검증 근거가 없으면 이를 `limitations`에 명시한다. Q&A 출력은 설명 전용이며
`ThesisAnalysisResult`의 점수·상태 계산에 사용하지 않는다.
