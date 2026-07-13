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
`impact`, `reason`, `published_at`을 제공한다. `SUPPORT`와 `CONTRADICT`에는 `source_url` 또는
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

그래프 내부용 재시도 횟수, 모델 출력 객체, 포트폴리오 문맥은 추가 필드로만 관리하며 B에 노출하지 않는다.
