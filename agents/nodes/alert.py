"""Rule-based Alert Decision node."""

from agents.policy import decide_alert
from agents.state import AnalysisState


def alert_decision(state: AnalysisState, *, major_movement_threshold: int | None = None) -> dict:
    return {
        "alert_decision": decide_alert(
            state["thesis_snapshot"].status,
            state["updated_status"],
            major_movement_threshold=major_movement_threshold,
        )
    }
