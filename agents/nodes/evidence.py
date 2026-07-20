"""Evidence extraction and classification node."""

from __future__ import annotations

import asyncio

from langgraph.runtime import Runtime

from agents.evidence_policy import (
    classification_from_findings,
    deterministic_finding,
    impact_from_findings,
    relevance_from_findings,
)
from agents.logic_graph import normalize_logic_graph, research_target_assumption_node_ids
from agents.models import (
    AssumptionAssessment,
    AssumptionFinding,
    EvidenceAssessment,
    EvidenceClassification,
    EvidenceImpact,
    EvidenceItem,
    SourceDocument,
)
from agents.runtime import AgentDependencies, call_model
from agents.sanitization import normalize_korean_summary, safe_source_snippet
from agents.state import AnalysisState


async def classify_evidence(state: AnalysisState, runtime: Runtime[AgentDependencies]) -> dict:
    unique_documents: dict[str, SourceDocument] = {}
    historical_document_ids = set(state.get("evidence_history_document_ids", []))
    if state.get("selected_documents") is not None:
        for document in state["selected_documents"]:
            unique_documents.setdefault(document.document_id, document)
    else:
        research_data = state["research_data"]
        for key in ("filings", "news", "macro"):
            for document in research_data[key]:
                unique_documents.setdefault(document.document_id, document)

    async def classify(document: SourceDocument) -> EvidenceItem:
        model_failed = False
        try:
            assessment = await call_model(
                runtime.context,
                runtime.context.model.classify_evidence,
                state["thesis_snapshot"],
                document,
                state.get("evidence_history_summary", ""),
            )
        except Exception as exc:
            model_failed = True
            assessment = EvidenceAssessment(
                classification=EvidenceClassification.UNCERTAIN,
                impact=EvidenceImpact.LOW,
                relevance_score=0,
                reason=f"분류 모델 오류({type(exc).__name__})로 불확실 처리했습니다.",
                related_assumptions=state["thesis_snapshot"].key_assumptions,
                source_excerpt=safe_source_snippet(
                    document.content, document.title, max_length=500
                ),
                content_snippet="분류 모델 오류로 근거 요약을 생성하지 못했습니다.",
            )
        allowed_assumptions = set(state["thesis_snapshot"].key_assumptions)
        related_assumptions = [
            assumption
            for assumption in assessment.related_assumptions
            if assumption in allowed_assumptions
        ]
        assessment = assessment.model_copy(update={"related_assumptions": related_assumptions})
        findings_by_assumption = {
            finding.assumption: finding
            for finding in assessment.assumption_findings
            if finding.assumption in allowed_assumptions
        }
        assumption_findings = []
        for assumption in state["thesis_snapshot"].key_assumptions:
            finding = findings_by_assumption.get(assumption)
            if finding is None:
                fallback_assessment = (
                    {
                        EvidenceClassification.SUPPORT: AssumptionAssessment.SUPPORT,
                        EvidenceClassification.CONTRADICT: AssumptionAssessment.CONTRADICT,
                    }.get(assessment.classification, AssumptionAssessment.NOT_ADDRESSED)
                    if assumption in related_assumptions
                    else AssumptionAssessment.NOT_ADDRESSED
                )
                finding = AssumptionFinding(
                    assumption=assumption,
                    assessment=fallback_assessment,
                    impact=EvidenceImpact.LOW,
                    relevance_score=0,
                    reasoning=(
                        assessment.reason
                        if fallback_assessment != AssumptionAssessment.NOT_ADDRESSED
                        else "이 정보는 해당 가정을 직접 검증하지 않습니다."
                    ),
                )
            assumption_findings.append(
                deterministic_finding(
                    assumption=assumption,
                    assessment=finding.assessment,
                    source_passage_indices=list(finding.source_passage_indices),
                    source_type=document.source_type,
                    invalid_reason=(
                        "해당 노드 판정을 뒷받침하는 원문 구간이 없어 점수에서 제외했습니다."
                        if finding.assessment
                        in {AssumptionAssessment.SUPPORT, AssumptionAssessment.CONTRADICT}
                        else None
                    ),
                )
            )
        assessment = assessment.model_copy(
            update={
                "classification": (
                    EvidenceClassification.UNCERTAIN
                    if model_failed
                    else classification_from_findings(assumption_findings)
                ),
                "impact": impact_from_findings(assumption_findings),
                "relevance_score": relevance_from_findings(assumption_findings),
                "related_assumptions": [
                    finding.assumption
                    for finding in assumption_findings
                    if finding.assessment != AssumptionAssessment.NOT_ADDRESSED
                ],
                "assumption_findings": assumption_findings,
            }
        )
        assessment = assessment.model_copy(
            update={"content_snippet": normalize_korean_summary(assessment.content_snippet)}
        )
        directional = assessment.classification in {
            EvidenceClassification.SUPPORT,
            EvidenceClassification.CONTRADICT,
        }
        has_directional_findings = any(
            finding.assessment in {AssumptionAssessment.SUPPORT, AssumptionAssessment.CONTRADICT}
            for finding in assessment.assumption_findings
        )
        if (
            (directional or has_directional_findings)
            and document.source_url is None
            and document.vector_doc_id is None
        ):
            assessment = assessment.model_copy(
                update={
                    "classification": EvidenceClassification.UNCERTAIN,
                    "impact": EvidenceImpact.LOW,
                    "reason": "출처 참조가 없어 방향성 판정을 보류했습니다.",
                    "assumption_findings": [
                        finding.model_copy(
                            update={
                                "assessment": AssumptionAssessment.NOT_ADDRESSED,
                                "impact": EvidenceImpact.LOW,
                                "relevance_score": 0,
                                "reasoning": "출처 참조가 없어 노드 방향성 판정을 보류했습니다.",
                            }
                        )
                        for finding in assessment.assumption_findings
                    ],
                }
            )
        return EvidenceItem(
            document_id=document.document_id,
            source_type=document.source_type,
            source_url=document.source_url,
            vector_doc_id=document.vector_doc_id,
            content_snippet=assessment.content_snippet,
            classification=assessment.classification,
            impact=assessment.impact,
            reason=assessment.reason,
            related_assumptions=assessment.related_assumptions,
            assumption_findings=assessment.assumption_findings,
            published_at=document.published_at,
        )

    cached = {item.document_id: item for item in state.get("evidence_list", [])}
    new_documents = [
        document
        for document in unique_documents.values()
        if document.document_id not in cached
        and document.document_id not in historical_document_ids
    ]
    new_evidence = await asyncio.gather(*(classify(doc) for doc in new_documents))
    cached.update({item.document_id: item for item in new_evidence})
    # Keep evidence found in earlier research rounds. Replacing this list with only
    # the current round made valid evidence appear and disappear between rounds.
    evidence = list(cached.values())
    graph = normalize_logic_graph(
        state["thesis_snapshot"].logic_graph,
        main_thesis=state["thesis_snapshot"].main_thesis,
        key_assumptions=state["thesis_snapshot"].key_assumptions,
    )
    target_node_ids = research_target_assumption_node_ids(graph)
    node_id_by_assumption = {
        (node.assumption or node.label): node.node_id
        for node in graph.nodes
        if node.kind == "ASSUMPTION"
    }
    satisfied_node_ids = {
        score.node_id
        for score in (
            state["thesis_snapshot"].score_breakdown.assumption_scores
            if state["thesis_snapshot"].score_breakdown
            else []
        )
        if score.has_evidence
    }
    for item in evidence:
        directional_findings = {
            finding.assumption
            for finding in item.assumption_findings
            if finding.assessment in {AssumptionAssessment.SUPPORT, AssumptionAssessment.CONTRADICT}
            and finding.source_passage_indices
        }
        # Compatibility for directional records created before per-assumption findings.
        if not item.assumption_findings and item.classification in {
            EvidenceClassification.SUPPORT,
            EvidenceClassification.CONTRADICT,
        }:
            directional_findings.update(item.related_assumptions)
        satisfied_node_ids.update(
            node_id_by_assumption[assumption]
            for assumption in directional_findings
            if assumption in node_id_by_assumption
        )

    unresolved_node_ids = target_node_ids - satisfied_node_ids
    focus_points = [
        node.assumption or node.label
        for node in graph.nodes
        if node.node_id in unresolved_node_ids and node.kind == "ASSUMPTION"
    ]
    target_count = len(target_node_ids)
    coverage_percent = (
        len(target_node_ids & satisfied_node_ids) / target_count * 100 if target_count else 100.0
    )
    needs_more = bool(unresolved_node_ids)
    return {
        "evidence_list": evidence,
        "needs_more_research": needs_more,
        "focus_points": focus_points,
        "required_node_coverage_percent": round(coverage_percent, 1),
        "unresolved_required_assumptions": focus_points,
    }
