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
노출하지 않는다. `EvidenceAssessment.relevance_score`는 0.0~1.0의 모델 출력이며,
기본 0.55 미만의 SUPPORT/CONTRADICT 판정은 Evidence 노드에서 NEUTRAL/LOW로 강등한다.
`impact`는 별도 materiality 필드를 추가하지 않고 기존 HIGH/MEDIUM/LOW 중요도 계약을
그대로 사용한다.
`EvidenceModelOutput.assumption_findings`는 각 핵심 가정을 원문 전체와 대조한 내부 판정이다.
각 항목은 가정 원문, SUPPORT/CONTRADICT/MIXED/NOT_ADDRESSED, 영향도, 관련도, 판단 이유와
근거 구간 번호를 가진다. 방향성 가정 판정이 있으면 문서 전체 판정이 NEUTRAL이더라도 Agent가
방향성을 다시 일치시켜 단편적인 종합 판정이 핵심 신호를 덮지 않도록 한다.
모델 내부 출력인 `EvidenceModelOutput.source_passage_indices`는 Agent가 미리 번호를 붙인 원문
구간 중 최대 3개를 가리킨다. Agent는 이 번호로 실제 구간을 다시 찾아 `EvidenceAssessment.source_excerpt`에
넣으므로, 모델이 원문을 글자 단위로 재현할 필요가 없다. 표시용 한국어 요약만
`EvidenceItem.content_snippet`에 저장하며 요약 생성 실패는 분류 결과와 분리해서 처리한다.

`evidence_history_summary`는 백엔드가 종목별 Markdown 파일로 물질화한 과거 근거·판단
요약이며 파일 내용 그대로 분류/Bull/Bear/Judge 프롬프트에 전달한다. 이 문맥은 현재
종목의 스토리와 새 정보의 연속성·반전·구체화를 파악하기 위한 용도일 뿐 점수 입력이
아니다. 과거 근거는 현재 Thesis 기준점에 이미 반영된 것으로 취급한다.
`evidence_history_document_ids`에 포함된 동일 문서는 Evidence 노드가 모델 호출 전에
NEUTRAL/LOW로 중복 제외하여 한 정보가 여러 분석에서 반복 가산되지 않게 한다.

그래프 내부용 재시도 횟수, 모델 출력 객체, 포트폴리오 문맥은 추가 필드로만 관리하며 B에 노출하지 않는다.
