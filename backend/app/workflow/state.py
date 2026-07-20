"""Shared state that flows through every node of the analysis graph."""
from typing import TypedDict


class NewsItem(TypedDict):
    id: str
    headline: str
    body: str


class ExtractedEvidence(TypedDict):
    news_id: str
    source_text: str
    extracted_claim: str
    related_premise: str


class ClassifiedEvidence(TypedDict):
    news_id: str
    source_text: str
    related_premise: str
    classification: str  # SUPPORT / CONTRADICT / NEUTRAL / UNCERTAIN
    impact: str  # HIGH / MEDIUM / LOW
    reasoning: str


class ThesisWorkflowState(TypedDict, total=False):
    # --- inputs (filled before graph.invoke) ---
    ticker: str
    main_thesis: str
    key_premises: list[str]
    risks: list[str]
    previous_confidence: int
    previous_status: str

    # --- populated by nodes, in pipeline order ---
    raw_news: list[NewsItem]
    extracted_evidence: list[ExtractedEvidence]
    classified_evidence: list[ClassifiedEvidence]
    bull_result: dict
    bear_result: dict
    judge_result: dict
