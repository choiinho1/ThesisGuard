"""Portfolio Q&A golden-set contracts and loader."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field

from agents.models import ContractModel, PortfolioQueryEvidence, PortfolioThesis

DEFAULT_PORTFOLIO_QA_DATASET = Path(__file__).resolve().parent / "datasets" / "portfolio_qa_v1.json"


class PortfolioQABenchmarkCase(ContractModel):
    case_id: str = Field(min_length=1)
    question: str = Field(min_length=1, max_length=500)
    portfolio_theses: list[PortfolioThesis] = Field(min_length=1)
    evidence: list[PortfolioQueryEvidence] = Field(default_factory=list)
    expected_document_ids: list[str] = Field(default_factory=list)
    required_limitation_keywords: list[str] = Field(default_factory=list)
    forbidden_answer_terms: list[str] = Field(default_factory=list)


def load_portfolio_qa_cases(
    path: Path = DEFAULT_PORTFOLIO_QA_DATASET,
) -> list[PortfolioQABenchmarkCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = [PortfolioQABenchmarkCase.model_validate(item) for item in payload]
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Portfolio Q&A benchmark case_id values must be unique")
    return cases
