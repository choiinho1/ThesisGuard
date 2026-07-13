"""SEC MCP — company filings via SEC EDGAR (no API key required).

SEC requires every request to carry an identifying User-Agent
(``SEC_USER_AGENT`` in .env) — requests without one are rate-limited or
blocked. All functions fail soft: on any HTTP/parse error they return an
empty list/dict instead of raising, because a single failed source must
not stop the rest of the research pipeline (see workflow.py `_run_research`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import httpx

from thesisguard_backend.config import get_settings

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_FULL_TEXT_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"

_cik_cache: dict[str, str] | None = None


def _headers() -> dict[str, str]:
    return {"User-Agent": get_settings().sec_user_agent}


@dataclass(slots=True)
class FilingRecord:
    accession_number: str
    form: str
    filed_at: datetime | None
    title: str
    url: str


@dataclass(slots=True)
class FilingSearchHit:
    accession_number: str
    form: str
    filed_at: datetime | None
    title: str
    excerpt: str
    url: str


async def _lookup_cik(ticker: str) -> str | None:
    global _cik_cache
    if _cik_cache is None:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(_TICKERS_URL, headers=_headers())
            response.raise_for_status()
            payload = response.json()
        _cik_cache = {
            row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in payload.values()
        }
    return _cik_cache.get(ticker.upper())


async def get_filings(ticker: str, limit: int = 5) -> list[FilingRecord]:
    """Most recent filings (10-K/10-Q/8-K priority) for a ticker."""

    try:
        cik = await _lookup_cik(ticker)
        if cik is None:
            return []
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(_SUBMISSIONS_URL.format(cik=cik), headers=_headers())
            response.raise_for_status()
            payload = response.json()

        recent = payload.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])

        priority_forms = {"10-K", "10-Q", "8-K"}
        records: list[FilingRecord] = []
        for form, filed_date, accession, primary_doc in zip(
            forms, dates, accessions, primary_docs, strict=False
        ):
            if form not in priority_forms:
                continue
            accession_nodash = accession.replace("-", "")
            url = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                f"{accession_nodash}/{primary_doc}"
            )
            records.append(
                FilingRecord(
                    accession_number=accession,
                    form=form,
                    filed_at=datetime.fromisoformat(filed_date) if filed_date else None,
                    title=f"{ticker.upper()} {form} ({filed_date})",
                    url=url,
                )
            )
            if len(records) >= limit:
                break
        return records
    except (httpx.HTTPError, KeyError, ValueError):
        return []


async def search_filing(ticker: str, query: str, limit: int = 5) -> list[FilingSearchHit]:
    """Full-text search across filings for a keyword (EDGAR full text search)."""

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                _FULL_TEXT_SEARCH_URL,
                params={"q": query, "forms": "10-K,10-Q,8-K", "entityName": ticker},
                headers=_headers(),
            )
            response.raise_for_status()
            payload = response.json()

        hits = payload.get("hits", {}).get("hits", [])[:limit]
        results: list[FilingSearchHit] = []
        for hit in hits:
            source = hit.get("_source", {})
            accession = hit.get("_id", "").split(":")[0]
            filed_date = source.get("file_date")
            results.append(
                FilingSearchHit(
                    accession_number=accession,
                    form=source.get("form", ""),
                    filed_at=datetime.fromisoformat(filed_date) if filed_date else None,
                    title=source.get("display_names", [ticker])[0],
                    excerpt=" ".join(source.get("ciks", [])) or query,
                    url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&filenum={accession}",
                )
            )
        return results
    except (httpx.HTTPError, KeyError, ValueError, IndexError):
        return []


async def get_company_facts(ticker: str) -> dict:
    """Structured XBRL financial facts (revenue, EPS, etc.) for a ticker."""

    try:
        cik = await _lookup_cik(ticker)
        if cik is None:
            return {}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(_FACTS_URL.format(cik=cik), headers=_headers())
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError):
        return {}
