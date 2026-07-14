from __future__ import annotations

import pytest

from agents.model import LangChainAnalysisModel
from agents.models import (
    EvidenceClassification,
    EvidenceImpact,
    EvidenceModelOutput,
    EvidenceSourceType,
    SourceDocument,
    StructuredThesis,
)


class _CapturingRunnable:
    def __init__(self) -> None:
        self.messages = []

    async def ainvoke(self, messages, config=None):  # type: ignore[no-untyped-def]
        del config
        self.messages = messages
        return EvidenceModelOutput(
            classification=EvidenceClassification.SUPPORT,
            impact=EvidenceImpact.MEDIUM,
            relevance_score=0.8,
            reason="현재 문서의 신규 변화가 가정을 지지합니다.",
            related_assumptions=["CAPEX 증가"],
            source_passage_indices=[0],
            content_snippet="현재 문서에서 새로운 CAPEX 증가가 확인됐습니다.",
        )


class _CapturingChatModel:
    def __init__(self, runnable: _CapturingRunnable) -> None:
        self.runnable = runnable

    def with_structured_output(self, schema):  # type: ignore[no-untyped-def]
        del schema
        return self.runnable


@pytest.mark.asyncio
async def test_history_file_content_is_sent_as_non_scoring_prompt_context() -> None:
    runnable = _CapturingRunnable()
    model = LangChainAnalysisModel(_CapturingChatModel(runnable))  # type: ignore[arg-type]
    thesis = StructuredThesis(
        raw_input="클라우드 CAPEX 증가가 장기적인 반도체 수요를 만든다.",
        main_thesis="클라우드 CAPEX 기반 수요 성장",
        key_assumptions=["CAPEX 증가"],
    )
    document = SourceDocument(
        document_id="new-doc",
        source_type=EvidenceSourceType.NEWS,
        source_url="https://example.com/new-doc",
        title="신규 CAPEX",
        content="A new cloud provider budget raised capital expenditure by 20 percent.",
    )
    history = "# NVDA 근거 히스토리\n과거에는 데이터센터 매출이 증가했습니다."

    await model.classify_evidence(thesis, document, history)

    system_prompt = runnable.messages[0].content
    task_prompt = runnable.messages[1].content
    assert "Never count the same fact twice" in system_prompt
    assert "already reflected in the previous thesis confidence" in system_prompt
    assert history in task_prompt
    assert 'role="narrative_only_non_scoring"' in task_prompt
    assert "only the incremental information" in task_prompt
