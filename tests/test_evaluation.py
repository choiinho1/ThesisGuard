from agents.evaluation import accuracy, citation_groundedness, contradiction_recall
from agents.models import (
    EvidenceClassification,
    EvidenceImpact,
    EvidenceItem,
    EvidenceSourceType,
)


def evidence(classification: EvidenceClassification) -> EvidenceItem:
    return EvidenceItem(
        document_id="doc-1",
        source_type=EvidenceSourceType.SEC_FILING,
        source_url="https://example.com/doc-1",
        content_snippet="Revenue increased.",
        classification=classification,
        impact=EvidenceImpact.HIGH,
        reason="실적 수치가 전제와 직접 연결됩니다.",
    )


def test_evaluation_metrics() -> None:
    item = evidence(EvidenceClassification.CONTRADICT)

    assert accuracy(["SUPPORT", "CONTRADICT"], ["SUPPORT", "CONTRADICT"]) == 1
    assert citation_groundedness([item], {"doc-1": "The report states: Revenue increased."}) == 1
    assert contradiction_recall({"doc-1"}, [item]) == 1
