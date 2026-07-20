"""
Node 5/6: Bear Agent - REAL LLM CALL.

Mirror of node_bull_analysis.py: argues the strongest reasonable case AGAINST
the thesis, from the same classified evidence.
"""
from ..llm_client import call_structured
from .state import ThesisWorkflowState

BEAR_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "argument": {
            "type": "string",
            "description": "The bear case for why the thesis is weakening or broken, in Korean.",
        },
        "key_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3-5 bullet points backing the bear case, in Korean.",
        },
        "suggested_confidence_delta": {
            "type": "integer",
            "description": "Bear agent's suggested change to the confidence score (-100 to 100), from its pessimistic viewpoint.",
        },
    },
    "required": ["argument", "key_points", "suggested_confidence_delta"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are the Bear Agent in ThesisGuard's Agentic Debate. Given a thesis and a "
    "batch of classified evidence, make the strongest reasonable case that the "
    "thesis is weakening or broken. You may not invent facts not present in the "
    "evidence, but you should argue your side persuasively - a Bull Agent argues "
    "the opposite, and a Judge Agent weighs both. Respond in Korean."
)


def run_bear_analysis(state: ThesisWorkflowState) -> ThesisWorkflowState:
    evidence_block = "\n\n".join(
        f"[{ev['news_id']}] classification={ev['classification']} impact={ev['impact']}\n"
        f"reasoning: {ev['reasoning']}"
        for ev in state["classified_evidence"]
    )

    user_content = (
        f"Main Thesis: {state['main_thesis']}\n"
        f"Current Confidence Score: {state['previous_confidence']}\n\n"
        f"Classified Evidence:\n\n{evidence_block}\n\n"
        "Make the bear case."
    )

    state["bear_result"] = call_structured(
        system=SYSTEM_PROMPT,
        user_content=user_content,
        tool_name="bear_case",
        tool_schema=BEAR_TOOL_SCHEMA,
    )
    return state
