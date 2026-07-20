from __future__ import annotations

import pytest

from agents.model import LangChainAnalysisModel
from agents.models import (
    DebateReport,
    EvidenceClassification,
    EvidenceImpact,
    EvidenceItem,
    EvidenceModelFinding,
    EvidenceModelOutput,
    EvidenceSourceType,
    JudgeExplanation,
    SourceDocument,
    StructuredThesis,
    ThesisScoreBreakdown,
)


class _CapturingRunnable:
    def __init__(self) -> None:
        self.messages = []

    async def ainvoke(self, messages, config=None):  # type: ignore[no-untyped-def]
        del config
        self.messages = messages
        return EvidenceModelOutput(
            assumption_findings=[
                EvidenceModelFinding(
                    assumption="CAPEX 증가",
                    assessment="SUPPORT",
                    source_passage_indices=[0],
                )
            ],
            content_snippet="현재 문서에서 새로운 CAPEX 증가가 확인됐습니다.",
        )


class _CapturingChatModel:
    def __init__(self, runnable: _CapturingRunnable) -> None:
        self.runnable = runnable

    def with_structured_output(self, schema):  # type: ignore[no-untyped-def]
        del schema
        return self.runnable


class _JudgeCapturingRunnable:
    def __init__(self) -> None:
        self.messages = []

    async def ainvoke(self, messages, config=None):  # type: ignore[no-untyped-def]
        del config
        self.messages = messages
        return JudgeExplanation(
            change_reason="기존에는 성장을 기대했고, 이번에는 실제 성장세가 확인됐습니다.",
            judge_summary="새로 확인된 성장세가 기존 기대를 뒷받침했습니다.",
        )


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


@pytest.mark.asyncio
async def test_judge_prompt_requires_plain_evidence_effect_and_before_after_change() -> None:
    runnable = _JudgeCapturingRunnable()
    model = LangChainAnalysisModel(_CapturingChatModel(runnable))  # type: ignore[arg-type]
    thesis = StructuredThesis(
        raw_input="클라우드 CAPEX 증가가 장기적인 반도체 수요를 만든다.",
        main_thesis="클라우드 CAPEX 기반 수요 성장",
        key_assumptions=["CAPEX 증가"],
    )
    evidence = EvidenceItem(
        document_id="new-doc",
        source_type=EvidenceSourceType.NEWS,
        source_url="https://example.com/new-doc",
        content_snippet="클라우드 사업자의 CAPEX가 증가했습니다.",
        classification=EvidenceClassification.SUPPORT,
        impact=EvidenceImpact.MEDIUM,
        reason="기존 기대와 같은 방향의 실제 지출 증가입니다.",
        related_assumptions=["CAPEX 증가"],
    )
    breakdown = ThesisScoreBreakdown(
        previous_score=0,
        health_score=6,
        score_delta=6,
        root_state=0.12,
        coverage_percent=100,
    )

    await model.judge(
        thesis,
        [evidence],
        DebateReport(summary="지출 증가가 기존 기대를 뒷받침합니다."),
        DebateReport(summary="뚜렷한 반대 내용은 없습니다."),
        breakdown,
    )

    task_prompt = runnable.messages[1].content
    assert "non-technical Korean user" in task_prompt
    assert "each new fact supports or weakens that expectation" in task_prompt
    assert "compare the before and after situations" in task_prompt
    assert "Do not merely restate a score change" in task_prompt
    assert "Never expose implementation language" in task_prompt
