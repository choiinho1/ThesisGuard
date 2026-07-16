from agents.evaluation import (
    accuracy,
    citation_groundedness,
    contradiction_recall,
    load_portfolio_qa_cases,
    portfolio_query_citation_precision,
    portfolio_query_citation_recall,
    portfolio_query_limitation_recall,
)
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


def test_portfolio_query_evaluation_metrics() -> None:
    assert portfolio_query_citation_precision({"doc-1", "doc-2"}, ["doc-1", "fake"]) == 0.5
    assert portfolio_query_citation_recall({"doc-1", "doc-2"}, ["doc-2"]) == 0.5
    assert (
        portfolio_query_limitation_recall({"MU", "근거"}, ["MU에는 비교 가능한 근거가 없습니다."])
        == 1
    )


def test_portfolio_query_golden_dataset_is_valid_and_covers_safety_cases() -> None:
    cases = load_portfolio_qa_cases()

    assert len(cases) >= 8
    assert len({case.case_id for case in cases}) == len(cases)
    assert any(not case.evidence for case in cases)
    assert any(case.required_limitation_keywords for case in cases)
    assert any("매수" in case.question or "매도" in case.question for case in cases)
    assert any(
        "ignore" in case.evidence[0].evidence.content_snippet.casefold()
        for case in cases
        if case.evidence
    )
