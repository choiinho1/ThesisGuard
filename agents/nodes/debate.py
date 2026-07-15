"""Bull and Bear reports plus a narrative-only Judge explanation."""

from __future__ import annotations

from langgraph.runtime import Runtime

from agents.evidence_policy import meaningful_directional_evidence
from agents.models import DebateReport, JudgeExplanation
from agents.runtime import AgentDependencies, call_model
from agents.state import AnalysisState


def debate_start(_: AnalysisState) -> dict:
    return {}


async def bull_agent(state: AnalysisState, runtime: Runtime[AgentDependencies]) -> dict:
    evidence = meaningful_directional_evidence(state["evidence_list"])
    try:
        report = await call_model(
            runtime.context,
            runtime.context.model.build_bull_report,
            state["thesis_snapshot"],
            evidence,
            state.get("evidence_history_summary", ""),
        )
    except Exception:
        report = DebateReport(summary="Bull Agent 설명 생성에 실패했습니다.")
    return {
        "bull_report": report.summary,
        "bull_report_data": report,
        "bull_evidence_document_ids": report.evidence_document_ids,
    }


async def bear_agent(state: AnalysisState, runtime: Runtime[AgentDependencies]) -> dict:
    evidence = meaningful_directional_evidence(state["evidence_list"])
    try:
        report = await call_model(
            runtime.context,
            runtime.context.model.build_bear_report,
            state["thesis_snapshot"],
            evidence,
            state.get("evidence_history_summary", ""),
        )
    except Exception:
        report = DebateReport(summary="Bear Agent 설명 생성에 실패했습니다.")
    return {
        "bear_report": report.summary,
        "bear_report_data": report,
        "bear_evidence_document_ids": report.evidence_document_ids,
    }


async def judge_agent(state: AnalysisState, runtime: Runtime[AgentDependencies]) -> dict:
    directional = meaningful_directional_evidence(state["evidence_list"])
    thesis = state["thesis_snapshot"]
    if not directional:
        decision = JudgeExplanation(
            change_reason=state["deterministic_change_reason"],
            judge_summary="점수에 반영할 새로운 방향성 근거가 없어 기존 가정 상태를 유지했습니다.",
            observation_points=state.get("focus_points", []),
        )
    else:
        try:
            decision = await call_model(
                runtime.context,
                runtime.context.model.judge,
                thesis,
                directional,
                state["bull_report_data"],
                state["bear_report_data"],
                state["score_breakdown"],
                state.get("evidence_history_summary", ""),
            )
        except Exception:
            decision = JudgeExplanation(
                change_reason=state["deterministic_change_reason"],
                judge_summary=(
                    "Judge 설명 생성에 실패했지만 점수는 결정론적 계산 결과를 유지했습니다."
                ),
                observation_points=state.get("focus_points", []),
            )
    return {
        "judge_report": decision.judge_summary,
        "judge_decision": decision,
        "change_reason": decision.change_reason,
        "conflicting_assumptions": state["deterministic_conflicting_assumptions"],
        "observation_points": decision.observation_points,
    }
