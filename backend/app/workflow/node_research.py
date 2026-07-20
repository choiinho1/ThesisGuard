"""
Node 1/6: Research.

*** THIS NODE IS 100% MOCK - NO LLM CALL, NO EXTERNAL API. ***
It stands in for what would eventually be Filing Agent / News Agent / Macro
Agent hitting SEC EDGAR, a news API, and a macro data provider. For this
prototype it just returns a hand-written set of "news" items per ticker so
the rest of the pipeline (which DOES call the real OpenAI API) has something
realistic to chew on.

Swap `MOCK_NEWS_DB` for a real fetch_news(ticker) call later without touching
any other node - that's the entire point of keeping this as its own file.
"""
from .state import ThesisWorkflowState, NewsItem

MOCK_NEWS_DB: dict[str, list[NewsItem]] = {
    "AVGO": [
        {
            "id": "news-1",
            "headline": "Major hyperscaler raises AI datacenter capex guidance",
            "body": (
                "A major hyperscaler raised its AI datacenter capital expenditure guidance for "
                "next fiscal year, and reaffirmed a multi-year custom AI ASIC roadmap with "
                "Broadcom named as the lead co-design partner for its next-generation training "
                "accelerator."
            ),
        },
        {
            "id": "news-2",
            "headline": "Hyperscaler diversifies custom silicon vendor base",
            "body": (
                "A hyperscaler customer is reported to be shifting a portion of its next-generation "
                "custom AI chip design work away from Broadcom toward a rival ASIC design house, "
                "in a move described internally as vendor risk diversification."
            ),
        },
        {
            "id": "news-3",
            "headline": "Broadcom networking silicon shipments delayed one quarter",
            "body": (
                "Broadcom's networking division reported a one-quarter shipment delay for its "
                "next-generation switch silicon due to advanced packaging capacity constraints, "
                "while reaffirming its full-year revenue outlook."
            ),
        },
    ],
    "NVDA": [
        {
            "id": "news-1",
            "headline": "Hyperscaler capex guidance raised for AI infrastructure",
            "body": (
                "Multiple hyperscalers raised FY capex guidance citing continued GPU cluster "
                "buildout for large-scale AI training workloads."
            ),
        },
        {
            "id": "news-2",
            "headline": "Growing uncertainty around custom silicon substitution",
            "body": (
                "Several large cloud providers expanded internal custom AI accelerator programs, "
                "raising analyst questions about long-term merchant GPU demand growth rates."
            ),
        },
    ],
}

# Fallback used for any ticker not explicitly seeded above, so the graph never
# breaks during the demo regardless of which holding is analyzed.
_GENERIC_FALLBACK: list[NewsItem] = [
    {
        "id": "news-generic-1",
        "headline": "No ticker-specific mock news configured",
        "body": (
            "No mock news has been authored for this ticker yet. Add entries to "
            "MOCK_NEWS_DB in node_research.py, or wire this node up to a real "
            "news/filing API."
        ),
    }
]


def run_research(state: ThesisWorkflowState) -> ThesisWorkflowState:
    ticker = state["ticker"]
    state["raw_news"] = MOCK_NEWS_DB.get(ticker, _GENERIC_FALLBACK)
    return state
