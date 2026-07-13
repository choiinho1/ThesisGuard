"""Rule-based Alert Decision node."""

from agents.policy import decide_alert
from agents.state import AnalysisState


def alert_decision(state: AnalysisState) -> dict:
    return {
        "alert_decision": decide_alert(state["thesis_snapshot"].status, state["updated_status"])
    }
