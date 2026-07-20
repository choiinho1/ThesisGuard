"""
Portfolio Recommendation - REAL LLM CALL.

Not part of the analysis graph. Takes a free-text investment goal from the
user (risk tolerance, horizon, sector preference, whatever they write) and
asks the model to propose a concrete portfolio: tickers, weights, and a short
reason per holding. This is a single LLM call, same shape as
node_thesis_structuring.py.

CAVEAT (surfaced to the user in the API response, not swept under the rug):
the model has no live market data connection in this prototype - it is
reasoning from its own training knowledge, which has a cutoff date. Treat the
output as a reasonable starting draft, not real-time investment advice.
"""
from ..llm_client import call_structured

RECOMMENDATION_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "strategy_summary": {
            "type": "string",
            "description": "One or two sentence summary of the overall strategy behind this portfolio, in Korean.",
        },
        "holdings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker symbol, e.g. NVDA."},
                    "weight": {
                        "type": "number",
                        "description": "Target weight as a fraction of the total portfolio, e.g. 0.15 for 15%.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this holding fits the stated goal, in Korean.",
                    },
                },
                "required": ["ticker", "weight", "reason"],
                "additionalProperties": False,
            },
            "description": "5-8 holdings. Weights (including cash_ratio) should sum to approximately 1.0.",
        },
        "cash_ratio": {
            "type": "number",
            "description": "Target cash weight as a fraction of the total portfolio, e.g. 0.1 for 10%.",
        },
        "knowledge_cutoff_caveat": {
            "type": "string",
            "description": "A short Korean disclaimer noting this recommendation is based on the model's training knowledge, not live market data, and should be verified before acting on it.",
        },
    },
    "required": ["strategy_summary", "holdings", "cash_ratio", "knowledge_cutoff_caveat"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are the Portfolio Recommendation assistant for ThesisGuard. Given a "
    "user's free-text investment goal (risk tolerance, horizon, sector "
    "preferences, exclusions, anything they mention), propose a concrete "
    "starting portfolio: 5-8 real, currently-existing public company stock "
    "tickers with target weights. Do NOT include cash as an item in "
    "`holdings` - cash goes ONLY in the separate `cash_ratio` field. The sum "
    "of all `holdings[].weight` plus `cash_ratio` must equal approximately "
    "1.0. Give a short reason per holding tied to the stated goal. This is a "
    "draft for the user to refine, not a final recommendation - always "
    "include a caveat that you are reasoning from training knowledge, not "
    "live market data. Respond in Korean."
)


_CASH_ALIASES = {"CASH", "USD", "현금", "KRW"}


def recommend_portfolio(goal_text: str) -> dict:
    user_content = f"Investment goal:\n\"\"\"\n{goal_text}\n\"\"\"\n\nPropose a portfolio."
    result = call_structured(
        system=SYSTEM_PROMPT,
        user_content=user_content,
        tool_name="recommend_portfolio",
        tool_schema=RECOMMENDATION_TOOL_SCHEMA,
        max_tokens=2000,
    )

    # Belt-and-suspenders: despite the system prompt telling it not to, the
    # model sometimes still slips a "CASH" row into `holdings` in addition to
    # `cash_ratio`. Strip it here rather than relying on prompting alone, so
    # weights reliably sum to ~1.0.
    result["holdings"] = [
        h for h in result["holdings"] if h["ticker"].strip().upper() not in _CASH_ALIASES
    ]
    return result
