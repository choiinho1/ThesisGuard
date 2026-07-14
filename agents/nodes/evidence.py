"""Evidence extraction and classification node."""

from __future__ import annotations

import asyncio

from langgraph.runtime import Runtime

from agents.evidence_policy import meaningful_directional_evidence
from agents.models import (
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
        if document.document_id in historical_document_ids:
            return EvidenceItem(
                document_id=document.document_id,
                source_type=document.source_type,
                source_url=document.source_url,
                vector_doc_id=document.vector_doc_id,
                content_snippet=(
                    "과거 분석에서 이미 반영된 동일 문서이므로 "
                    "이번 판단에서 중복 제외했습니다."
                ),
                classification=EvidenceClassification.NEUTRAL,
                impact=EvidenceImpact.LOW,
                reason="동일 document_id의 과거 근거가 이미 현재 신뢰도에 반영되어 있습니다.",
                related_assumptions=[],
                published_at=document.published_at,
            )
        try:
            assessment = await call_model(
                runtime.context,
                runtime.context.model.classify_evidence,
                state["thesis_snapshot"],
                document,
                state.get("evidence_history_summary", ""),
            )
        except Exception as exc:
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
        directional = assessment.classification in {
            EvidenceClassification.SUPPORT,
            EvidenceClassification.CONTRADICT,
        }
        if directional and assessment.relevance_score < runtime.context.config.min_relevance_score:
            assessment = assessment.model_copy(
                update={
                    "classification": EvidenceClassification.NEUTRAL,
                    "impact": EvidenceImpact.LOW,
                    "reason": (
                        f"투자 논리 관련도 {assessment.relevance_score:.2f}로 "
                        "판정 기준에 미달했습니다."
                    ),
                }
            )
        assessment = assessment.model_copy(
            update={"content_snippet": normalize_korean_summary(assessment.content_snippet)}
        )
        directional = assessment.classification in {
            EvidenceClassification.SUPPORT,
            EvidenceClassification.CONTRADICT,
        }
        if directional and document.source_url is None and document.vector_doc_id is None:
            assessment = assessment.model_copy(
                update={
                    "classification": EvidenceClassification.UNCERTAIN,
                    "impact": EvidenceImpact.LOW,
                    "reason": "출처 참조가 없어 방향성 판정을 보류했습니다.",
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
            published_at=document.published_at,
        )

    cached = {item.document_id: item for item in state.get("evidence_list", [])}
    new_documents = [
        document for document in unique_documents.values() if document.document_id not in cached
    ]
    new_evidence = await asyncio.gather(*(classify(doc) for doc in new_documents))
    cached.update({item.document_id: item for item in new_evidence})
    evidence = [cached[document_id] for document_id in unique_documents]
    grounded = meaningful_directional_evidence(evidence)
    grounded_ids = {item.document_id for item in grounded}
    needs_more = len(grounded) < runtime.context.config.min_grounded_evidence
    focus_points = list(
        dict.fromkeys(
            assumption
            for item in evidence
            if item.document_id not in grounded_ids
            for assumption in item.related_assumptions
        )
    )
    if not focus_points and needs_more:
        focus_points = state["thesis_snapshot"].key_assumptions
    return {
        "evidence_list": evidence,
        "needs_more_research": needs_more,
        "focus_points": focus_points,
    }
