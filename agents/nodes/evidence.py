"""Evidence extraction and classification node."""

from __future__ import annotations

import asyncio

from langgraph.runtime import Runtime

from agents.models import (
    EvidenceAssessment,
    EvidenceClassification,
    EvidenceImpact,
    EvidenceItem,
    SourceDocument,
)
from agents.runtime import AgentDependencies, call_model
from agents.sanitization import safe_source_snippet, sanitize_source_text
from agents.state import AnalysisState


async def classify_evidence(state: AnalysisState, runtime: Runtime[AgentDependencies]) -> dict:
    unique_documents: dict[str, SourceDocument] = {}
    research_data = state["research_data"]
    for key in ("filings", "news", "macro"):
        for document in research_data[key]:
            unique_documents.setdefault(document.document_id, document)

    async def classify(document: SourceDocument) -> EvidenceItem:
        try:
            assessment = await call_model(
                runtime.context,
                runtime.context.model.classify_evidence,
                state["thesis_snapshot"],
                document,
            )
        except Exception as exc:
            assessment = EvidenceAssessment(
                classification=EvidenceClassification.UNCERTAIN,
                impact=EvidenceImpact.LOW,
                reason=f"분류 모델 오류({type(exc).__name__})로 불확실 처리했습니다.",
                related_assumptions=state["thesis_snapshot"].key_assumptions,
                content_snippet=safe_source_snippet(
                    document.content, document.title, max_length=500
                ),
            )
        cleaned_snippet = sanitize_source_text(assessment.content_snippet, max_length=2000)
        if not cleaned_snippet:
            cleaned_snippet = safe_source_snippet(
                document.content, document.title, max_length=500
            )
        assessment = assessment.model_copy(update={"content_snippet": cleaned_snippet})
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

    evidence = await asyncio.gather(*(classify(doc) for doc in unique_documents.values()))
    grounded = [
        item
        for item in evidence
        if item.classification
        in {EvidenceClassification.SUPPORT, EvidenceClassification.CONTRADICT}
    ]
    needs_more = len(grounded) < runtime.context.config.min_grounded_evidence
    focus_points = list(
        dict.fromkeys(
            assumption
            for item in evidence
            if item.classification == EvidenceClassification.UNCERTAIN
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
