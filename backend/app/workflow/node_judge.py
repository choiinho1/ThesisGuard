"""
Node 6/6: Judge Agent - REAL LLM CALL.

Synthesizes the Bull and Bear cases plus the underlying classified evidence
into a single verdict: a new confidence score, a status label, and an
explanation shaped like ThesisGuard's "explainable alert" format (what
changed / conflicting premises / overall judgment / watch points).

This node's output is what gets persisted as the next ThesisVersion row -
persistence itself happens back in main.py, not here, so this stays a pure
function of state -> state.
"""
from ..llm_client import call_structured
from .state import ThesisWorkflowState

STATUS_ENUM = [
    "STRONGLY_STRENGTHENED",
    "STRENGTHENED",
    "UNCHANGED",
    "WEAKENED",
    "STRONGLY_WEAKENED",
    "BROKEN",
]

JUDGE_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "new_confidence_score": {
            "type": "integer",
            "description": "Updated thesis confidence score, 0-100.",
        },
        "status": {"type": "string", "enum": STATUS_ENUM},
        "what_changed": {
            "type": "string",
            "description": "One to two sentences on what specifically changed, in Korean.",
        },
        "conflicting_premises": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Which key premises (verbatim) are now in question, if any.",
        },
        "overall_judgment": {
            "type": "string",
            "description": "A short synthesis of the bull/bear debate and why the judge sided the way it did, in Korean.",
        },
        "watch_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3-5 concrete things to monitor going forward, in Korean.",
        },
    },
    "required": [
        "new_confidence_score",
        "status",
        "what_changed",
        "conflicting_premises",
        "overall_judgment",
        "watch_points",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are the Judge Agent in ThesisGuard's Agentic Debate. You receive a Bull "
    "Agent argument and a Bear Agent argument, both grounded in the same "
    "classified evidence, plus the thesis's current confidence score. Weigh the "
    "evidence's credibility, recency, directness, and independence yourself - do "
    "not simply average the two agents' suggested deltas. Produce a final "
    "confidence score, a status label, and an explanation in the "
    "what-changed / conflicting-premises / overall-judgment / watch-points "
    "format ThesisGuard uses for its explainable alerts. Respond in Korean."
)


def run_judge(state: ThesisWorkflowState) -> ThesisWorkflowState:
    evidence_block = "\n\n".join(
        f"[{ev['news_id']}] classification={ev['classification']} impact={ev['impact']}\n"
        f"reasoning: {ev['reasoning']}"
        for ev in state["classified_evidence"]
    )

    user_content = (
        f"Main Thesis: {state['main_thesis']}\n"
        f"Key Premises: {state['key_premises']}\n"
        f"Current Confidence Score: {state['previous_confidence']}\n"
        f"Current Status: {state['previous_status']}\n\n"
        f"Classified Evidence:\n\n{evidence_block}\n\n"
        f"Bull Agent argument: {state['bull_result']['argument']}\n"
        f"Bull key points: {state['bull_result']['key_points']}\n\n"
        f"Bear Agent argument: {state['bear_result']['argument']}\n"
        f"Bear key points: {state['bear_result']['key_points']}\n\n"
        "Render your final verdict."
    )

    state["judge_result"] = call_structured(
        system=SYSTEM_PROMPT,
        user_content=user_content,
        tool_name="judge_verdict",
        tool_schema=JUDGE_TOOL_SCHEMA,
        max_tokens=2000,
    )
    return state
