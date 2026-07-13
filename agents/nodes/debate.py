"""Bull, Bear, and Judge Agentic Debate nodes."""

from __future__ import annotations

from langgraph.runtime import Runtime

from agents.models import (
    DebateReport,
    EvidenceClassification,
    JudgeDecision,
    ThesisStatus,
)
from agents.runtime import AgentDependencies, call_model
from agents.state import AnalysisState


def debate_start(_: AnalysisState) -> dict:
    return {}


async def bull_agent(state: AnalysisState, runtime: Runtime[AgentDependencies]) -> dict:
    try:
        report = await call_model(
            runtime.context,
            runtime.context.model.build_bull_report,
            state["thesis_snapshot"],
            state["evidence_list"],
        )
    except Exception:
        report = DebateReport(summary="Bull Agent 응답 실패로 지지 판단을 보류했습니다.")
    return {
        "bull_report": report.summary,
        "bull_report_data": report,
        "bull_evidence_document_ids": report.evidence_document_ids,
    }


async def bear_agent(state: AnalysisState, runtime: Runtime[AgentDependencies]) -> dict:
    try:
        report = await call_model(
            runtime.context,
            runtime.context.model.build_bear_report,
            state["thesis_snapshot"],
            state["evidence_list"],
        )
    except Exception:
        report = DebateReport(summary="Bear Agent 응답 실패로 반박 판단을 보류했습니다.")
    return {
        "bear_report": report.summary,
        "bear_report_data": report,
        "bear_evidence_document_ids": report.evidence_document_ids,
    }


async def judge_agent(state: AnalysisState, runtime: Runtime[AgentDependencies]) -> dict:
    directional = [
        item
        for item in state["evidence_list"]
        if item.classification
        in {EvidenceClassification.SUPPORT, EvidenceClassification.CONTRADICT}
    ]
    thesis = state["thesis_snapshot"]
    if not directional:
        decision = JudgeDecision(
            updated_confidence=thesis.confidence_score,
            updated_status=ThesisStatus.UNCHANGED,
            change_reason="검증 가능한 방향성 근거가 없어 기존 Thesis를 유지합니다.",
            judge_summary="신규 근거가 부족하여 판단을 보류했습니다.",
            observation_points=state.get("focus_points", []),
        )
    else:
        try:
            decision = await call_model(
                runtime.context,
                runtime.context.model.judge,
                thesis,
                state["evidence_list"],
                state["bull_report_data"],
                state["bear_report_data"],
            )
        except Exception:
            decision = JudgeDecision(
                updated_confidence=thesis.confidence_score,
                updated_status=ThesisStatus.UNCHANGED,
                change_reason="Judge Agent 재시도 실패로 기존 Thesis를 유지합니다.",
                judge_summary="판정 모델 응답을 검증할 수 없어 판단을 보류했습니다.",
                observation_points=state.get("focus_points", []),
            )
    return {
        "judge_report": decision.judge_summary,
        "judge_decision": decision,
        "updated_confidence": decision.updated_confidence,
        "updated_status": decision.updated_status,
        "change_reason": decision.change_reason,
        "conflicting_assumptions": decision.conflicting_assumptions,
        "observation_points": decision.observation_points,
    }
