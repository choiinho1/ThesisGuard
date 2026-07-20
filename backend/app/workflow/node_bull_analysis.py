"""
Node 4/6: Bull Agent - REAL LLM CALL.

Argues the most reasonable case FOR the thesis still holding, using only the
classified evidence produced so far. Deliberately one-sided by design - the
balance comes from combining this with node_bear_analysis.py output in the
Judge node, not from this node being "fair" on its own.
"""
from ..llm_client import call_structured
from .state import ThesisWorkflowState

BULL_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "argument": {
            "type": "string",
            "description": "The bull case for why the thesis remains intact or has strengthened, in Korean.",
        },
        "key_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3-5 bullet points backing the bull case, in Korean.",
        },
        "suggested_confidence_delta": {
            "type": "integer",
            "description": "Bull agent's suggested change to the confidence score (-100 to 100), from its optimistic viewpoint.",
        },
    },
    "required": ["argument", "key_points", "suggested_confidence_delta"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are the Bull Agent in ThesisGuard's Agentic Debate. Given a thesis and a "
    "batch of classified evidence, make the strongest reasonable case that the "
    "thesis is intact or strengthening. You may not invent facts not present in "
    "the evidence, but you should argue your side persuasively - a Bear Agent will "
    "argue the opposite, and a Judge Agent will weigh both. Respond in Korean."
)


def run_bull_analysis(state: ThesisWorkflowState) -> ThesisWorkflowState:
    evidence_block = "\n\n".join(
        f"[{ev['news_id']}] classification={ev['classification']} impact={ev['impact']}\n"
        f"reasoning: {ev['reasoning']}"
        for ev in state["classified_evidence"]
    )

    user_content = (
        f"Main Thesis: {state['main_thesis']}\n"
        f"Current Confidence Score: {state['previous_confidence']}\n\n"
        f"Classified Evidence:\n\n{evidence_block}\n\n"
        "Make the bull case."
    )

    state["bull_result"] = call_structured(
        system=SYSTEM_PROMPT,
        user_content=user_content,
        tool_name="bull_case",
        tool_schema=BULL_TOOL_SCHEMA,
    )
    return state
