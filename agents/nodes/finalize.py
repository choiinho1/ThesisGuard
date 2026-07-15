"""Build the single ThesisAnalysisResult returned to Backend(B)."""

from agents.models import ThesisAnalysisResult
from agents.state import AnalysisState


def finalize(state: AnalysisState) -> dict:
    result = ThesisAnalysisResult(
        portfolio_id=state["portfolio_id"],
        holding_id=state["holding_id"],
        ticker=state["ticker"],
        evidence=state["evidence_list"],
        bull_summary=state["bull_report"],
        bear_summary=state["bear_report"],
        judge_summary=state["judge_report"],
        updated_confidence=state["updated_confidence"],
        updated_status=state["updated_status"],
        score_breakdown=state["score_breakdown"],
        change_reason=state["change_reason"],
        conflicting_assumptions=state["conflicting_assumptions"],
        observation_points=state["observation_points"],
        concentration=state["portfolio_analysis"],
        alert_decision=state["alert_decision"],
        research_rounds=state["research_round"],
        source_errors=list(dict.fromkeys(state.get("source_errors", []))),
    )
    return {"result": result}
