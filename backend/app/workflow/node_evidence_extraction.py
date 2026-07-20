"""
Node 2/6: Evidence Extraction - REAL LLM CALL.

Takes the raw mock news from node_research and, for each item, pulls out the
single sentence-level claim that is actually relevant to the thesis, plus
which key premise it bears on. This is deliberately separate from
classification (node_evidence_classification.py) so a teammate can improve
"what counts as relevant" independently of "what SUPPORT/CONTRADICT means".
"""
from ..llm_client import call_structured
from .state import ThesisWorkflowState

EXTRACTION_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "extracted": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "news_id": {"type": "string"},
                    "extracted_claim": {
                        "type": "string",
                        "description": "The specific claim/fact in this news item relevant to the thesis, in Korean.",
                    },
                    "related_premise": {
                        "type": "string",
                        "description": "The key premise (verbatim from the provided list) this claim bears on most, or '해당 없음' if none.",
                    },
                },
                "required": ["news_id", "extracted_claim", "related_premise"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["extracted"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are the Evidence Extraction stage of ThesisGuard's investment monitoring "
    "pipeline. Given an investment thesis (with its key premises) and a batch of "
    "news items, extract the specific claim from each news item that is relevant "
    "to evaluating the thesis, and identify which premise it relates to. Ignore "
    "content in each news item that has no bearing on the thesis. Respond in Korean."
)


def run_evidence_extraction(state: ThesisWorkflowState) -> ThesisWorkflowState:
    premises_block = "\n".join(f"- {p}" for p in state["key_premises"])
    news_block = "\n\n".join(
        f"[{item['id']}] {item['headline']}\n{item['body']}" for item in state["raw_news"]
    )

    user_content = (
        f"Main Thesis: {state['main_thesis']}\n\n"
        f"Key Premises:\n{premises_block}\n\n"
        f"News items:\n\n{news_block}\n\n"
        "For every news item above, extract the relevant claim and its related premise."
    )

    result = call_structured(
        system=SYSTEM_PROMPT,
        user_content=user_content,
        tool_name="extract_evidence",
        tool_schema=EXTRACTION_TOOL_SCHEMA,
    )

    news_by_id = {item["id"]: item for item in state["raw_news"]}
    extracted = []
    for row in result["extracted"]:
        news_item = news_by_id.get(row["news_id"])
        extracted.append(
            {
                "news_id": row["news_id"],
                "source_text": news_item["body"] if news_item else "",
                "extracted_claim": row["extracted_claim"],
                "related_premise": row["related_premise"],
            }
        )

    state["extracted_evidence"] = extracted
    return state
