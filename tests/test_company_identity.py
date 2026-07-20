from __future__ import annotations

from datetime import UTC, datetime

from agents.company_identity import (
    CompanyMatchStatus,
    identity_embedding_prefix,
    resolve_company_identity,
)
from agents.models import EvidenceSourceType, SourceDocument, StructuredThesis
from agents.retrieval import preselect_documents


def _identity(*, legal_name: str = "Acme Inc.") -> dict[str, object]:
    return {
        "identifier_scheme": "SEC_CIK",
        "identifier": "0000123456",
        "ticker": "ACME",
        "exchanges": ["Nasdaq"],
        "legal_name": legal_name,
        "aliases": [legal_name, "Acme"],
        "industry": "Industrial Robotics",
        "official_domains": ["acme.example"],
    }


def _news(document_id: str, title: str, content: str) -> SourceDocument:
    return SourceDocument(
        document_id=document_id,
        source_type=EvidenceSourceType.NEWS,
        source_url=f"https://publisher.example/{document_id}",
        title=title,
        content=content,
        published_at=datetime(2026, 7, 20, tzinfo=UTC),
        metadata={"company_name": "Acme Inc.", "company_identity": _identity()},
    )


def test_identity_resolution_separates_match_ambiguous_and_mismatch() -> None:
    matched = _news(
        "matched",
        "Acme (NASDAQ: ACME) reports quarterly results",
        "Acme revenue increased as industrial robotics orders grew.",
    )
    ambiguous = _news(
        "ambiguous",
        "Acme opens a new office",
        "Acme announced a local hiring event without issuer or market identifiers.",
    ).model_copy(
        update={
            "metadata": {
                "company_name": "Acme Inc.",
                "company_identity": _identity(legal_name="Acme Inc."),
            }
        }
    )
    mismatch = _news(
        "mismatch",
        "Other Robotics launches a warehouse system",
        "The private company discussed automation demand.",
    )

    assert resolve_company_identity(matched, ticker="ACME").status == CompanyMatchStatus.MATCH
    assert (
        resolve_company_identity(ambiguous, ticker="ACME").status
        == CompanyMatchStatus.AMBIGUOUS
    )
    assert resolve_company_identity(mismatch, ticker="ACME").status == CompanyMatchStatus.MISMATCH


def test_preselection_excludes_ambiguous_company_news_and_records_match_evidence() -> None:
    thesis = StructuredThesis(
        raw_input="ACME robotics demand will grow.",
        main_thesis="Robotics demand drives ACME growth",
        key_assumptions=["industrial robotics orders grow"],
    )
    matched = _news(
        "matched",
        "Acme Inc. robotics revenue rises",
        "Acme Inc. reported higher industrial robotics orders and revenue.",
    )
    ambiguous = _news(
        "ambiguous",
        "Acme announces local event",
        "Acme held a community event.",
    )

    selected = preselect_documents(
        {"filings": [], "news": [ambiguous, matched], "macro": []},
        ticker="ACME",
        thesis=thesis,
        focus_points=thesis.key_assumptions,
        lookback_days=30,
        min_news_score=0,
        source_limits={"filings": 0, "news": 5, "macro": 0},
        now=datetime(2026, 7, 20, tzinfo=UTC),
    )

    assert [document.document_id for document in selected] == ["matched"]
    assert selected[0].metadata["identity_match"]["status"] == "MATCH"


def test_identity_prefix_carries_cik_ticker_exchange_and_legal_name_into_rag_text() -> None:
    document = _news("matched", "Acme Inc. update", "Acme Inc. reported results.")

    prefix = identity_embedding_prefix(document)

    assert "identifier=0000123456" in prefix
    assert "ticker=ACME" in prefix
    assert "exchange=Nasdaq" in prefix
    assert "legal_name=Acme Inc." in prefix
