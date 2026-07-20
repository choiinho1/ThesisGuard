"""
Thesis structuring - REAL LLM CALL.

Not part of the main analysis graph (research -> ... -> judge); this runs once,
synchronously, when a user first registers a natural-language investment
rationale for a holding (see POST /api/holdings/{id}/thesis in main.py).
Kept in the workflow package because it's the same "LLM node" shape as
everything else and a team member may want to fold it into the graph later
(e.g. to re-structure a thesis automatically after a BROKEN verdict).
"""
from ..llm_client import call_structured

STRUCTURE_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "main_thesis": {
            "type": "string",
            "description": "One or two sentence core investment thesis, in Korean.",
        },
        "key_premises": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3-5 falsifiable assumptions this thesis depends on, in Korean.",
        },
        "risks": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3-5 key risks that would invalidate the thesis, in Korean.",
        },
    },
    "required": ["main_thesis", "key_premises", "risks"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are an equity research assistant for ThesisGuard, a personal investment "
    "thesis-tracking tool. You convert a free-form investment rationale written by "
    "a retail investor into a structured investment thesis: a concise main thesis, "
    "the falsifiable premises it depends on, and the risks that would break it. "
    "Be concrete and specific to the ticker discussed - avoid generic boilerplate."
)


def structure_thesis(ticker: str, raw_text: str) -> dict:
    user_content = (
        f"Ticker: {ticker}\n\n"
        f"Investor's raw investment rationale:\n\"\"\"\n{raw_text}\n\"\"\"\n\n"
        "Extract the structured thesis."
    )
    return call_structured(
        system=SYSTEM_PROMPT,
        user_content=user_content,
        tool_name="structure_thesis",
        tool_schema=STRUCTURE_TOOL_SCHEMA,
    )
