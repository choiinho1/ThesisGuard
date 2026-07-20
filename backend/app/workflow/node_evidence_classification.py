"""
Node 3/6: Evidence Classification - REAL LLM CALL.

Classifies each extracted claim from node_evidence_extraction.py against the
thesis as SUPPORT / CONTRADICT / NEUTRAL / UNCERTAIN, with an impact level and
a one-line reasoning. This is the data that eventually gets persisted as rows
in the `evidence` table.
"""
from ..llm_client import call_structured
from .state import ThesisWorkflowState

CLASSIFICATION_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "classified": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "news_id": {"type": "string"},
                    "classification": {
                        "type": "string",
                        "enum": ["SUPPORT", "CONTRADICT", "NEUTRAL", "UNCERTAIN"],
                    },
                    "impact": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                    "reasoning": {
                        "type": "string",
                        "description": "Why this evidence gets this classification and impact, in Korean.",
                    },
                },
                "required": ["news_id", "classification", "impact", "reasoning"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["classified"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are the Evidence Classification stage of ThesisGuard. For each extracted "
    "claim, decide whether it SUPPORTs the thesis (strengthens a key premise), "
    "CONTRADICTs it (conflicts with a key premise), is NEUTRAL (no real bearing), "
    "or UNCERTAIN (not enough information to tell direction). Also assign an "
    "impact level (HIGH/MEDIUM/LOW) reflecting how material this would be if true. "
    "Respond in Korean."
)


def run_evidence_classification(state: ThesisWorkflowState) -> ThesisWorkflowState:
    premises_block = "\n".join(f"- {p}" for p in state["key_premises"])
    evidence_block = "\n\n".join(
        f"[{ev['news_id']}] related_premise={ev['related_premise']}\nclaim: {ev['extracted_claim']}"
        for ev in state["extracted_evidence"]
    )

    user_content = (
        f"Main Thesis: {state['main_thesis']}\n\n"
        f"Key Premises:\n{premises_block}\n\n"
        f"Extracted claims to classify:\n\n{evidence_block}\n\n"
        "Classify every claim above."
    )

    result = call_structured(
        system=SYSTEM_PROMPT,
        user_content=user_content,
        tool_name="classify_evidence",
        tool_schema=CLASSIFICATION_TOOL_SCHEMA,
    )

    extracted_by_id = {ev["news_id"]: ev for ev in state["extracted_evidence"]}
    classified = []
    for row in result["classified"]:
        ev = extracted_by_id.get(row["news_id"], {})
        classified.append(
            {
                "news_id": row["news_id"],
                "source_text": ev.get("source_text", ""),
                "related_premise": ev.get("related_premise", ""),
                "classification": row["classification"],
                "impact": row["impact"],
                "reasoning": row["reasoning"],
            }
        )

    state["classified_evidence"] = classified
    return state
