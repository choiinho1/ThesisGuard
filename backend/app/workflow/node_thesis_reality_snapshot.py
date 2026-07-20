"""
Thesis Reality Snapshot - REAL LLM CALL.

Used by the "다른 사람 포트폴리오 검증" flow (POST /api/portfolio-check): given
just a ticker (+ optional weight/context, and optionally a thesis the user
already wrote), do BOTH of the following in a single call:

  1. Infer the most plausible investment thesis for holding this ticker
     (main thesis / key premises / risks) - skipped if the caller already
     supplied one.
  2. Immediately judge whether that thesis still looks plausible "as of now",
     using only the model's own reasoning/knowledge.

This is intentionally a snapshot judgment, not the multi-agent
Research -> Evidence -> Bull -> Bear -> Judge pipeline in graph.py. That
pipeline compares a thesis against NEW evidence collected over time for a
thesis the user is actively tracking. This node instead answers a cheaper,
one-shot question: "does this holding's most likely rationale still hold up
today, based on what the model already knows?" It deliberately does NOT
claim to have live market/news data - see `caveats` in the output schema.
"""
from ..llm_client import call_structured

REALITY_STATUS_ENUM = ["STILL_VALID", "PARTIALLY_VALID", "QUESTIONABLE", "LIKELY_OUTDATED"]

REALITY_SNAPSHOT_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "main_thesis": {
            "type": "string",
            "description": "The most plausible investment thesis for this holding, in Korean.",
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
        "reality_status": {"type": "string", "enum": REALITY_STATUS_ENUM},
        "confidence_score": {
            "type": "integer",
            "description": "0-100 confidence that this thesis still holds up today.",
        },
        "reasoning": {
            "type": "string",
            "description": "Why this status/score, referencing which premises feel solid vs shaky, in Korean.",
        },
        "caveats": {
            "type": "string",
            "description": "Korean disclaimer that this judgment is based on training knowledge, not live market/news data, and may be stale.",
        },
    },
    "required": [
        "main_thesis",
        "key_premises",
        "risks",
        "reality_status",
        "confidence_score",
        "reasoning",
        "caveats",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are the Reality Snapshot assistant for ThesisGuard. Given a stock "
    "ticker (and optionally its portfolio weight and an existing thesis), "
    "infer the single most plausible reason an investor would currently hold "
    "it (or reuse the thesis given to you if one is supplied), break it into "
    "key premises and risks, and then judge - using only your own knowledge - "
    "whether that thesis still looks reasonable. Be honest about "
    "uncertainty: if you are not confident how a premise has evolved "
    "recently, say so in `reasoning` and reflect it in `confidence_score` "
    "rather than guessing confidently. Always fill `caveats` noting this is "
    "based on training knowledge, not live data. Respond in Korean."
)


def snapshot_thesis_reality(ticker: str, weight: float | None = None, existing_thesis: dict | None = None) -> dict:
    context_lines = [f"Ticker: {ticker}"]
    if weight is not None:
        context_lines.append(f"Portfolio weight: {weight}")
    if existing_thesis:
        context_lines.append(
            "Existing thesis to evaluate (do not replace it, judge it as-is):\n"
            f"  main_thesis: {existing_thesis.get('main_thesis')}\n"
            f"  key_premises: {existing_thesis.get('key_premises')}\n"
            f"  risks: {existing_thesis.get('risks')}"
        )
    else:
        context_lines.append("No thesis supplied - infer the most plausible one yourself.")

    user_content = "\n".join(context_lines) + "\n\nProduce the reality snapshot."

    return call_structured(
        system=SYSTEM_PROMPT,
        user_content=user_content,
        tool_name="thesis_reality_snapshot",
        tool_schema=REALITY_SNAPSHOT_TOOL_SCHEMA,
        max_tokens=1500,
    )
