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
_TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_FULL_TEXT_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"

_cik_cache: dict[str, str] | None = None
_company_name_cache: dict[str, str] | None = None
_exchange_cache: dict[str, str] | None = None
_submissions_cache: dict[str, dict] = {}


def _headers() -> dict[str, str]:
    return {"User-Agent": get_settings().sec_user_agent}


@dataclass(slots=True)
class FilingRecord:
    accession_number: str
    form: str
    filed_at: datetime | None
    title: str
    url: str
    cik: str | None = None
    company_name: str | None = None
    exchange: str | None = None
    company_identity: CompanyIdentity | None = None


@dataclass(frozen=True, slots=True)
class CompanyIdentity:
    """Canonical SEC issuer identity attached to every retrieved company document."""

    cik: str
    ticker: str
    legal_name: str
    exchanges: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    industry: str | None = None

    def as_metadata(self) -> dict[str, object]:
        return {
            "identifier_scheme": "SEC_CIK",
            "identifier": self.cik,
            "ticker": self.ticker,
            "exchanges": list(self.exchanges),
            "legal_name": self.legal_name,
            "aliases": list(self.aliases),
            "industry": self.industry or "",
            "official_domains": [],
        }


@dataclass(slots=True)
class FilingSearchHit:
    accession_number: str
    form: str
    filed_at: datetime | None
    title: str
    excerpt: str
    url: str


async def _load_company_index() -> None:
    global _cik_cache, _company_name_cache, _exchange_cache
    if _cik_cache is not None and _company_name_cache is not None and _exchange_cache is not None:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(_TICKERS_EXCHANGE_URL, headers=_headers())
            response.raise_for_status()
            payload = response.json()
        fields = payload.get("fields", [])
        rows = [dict(zip(fields, values, strict=False)) for values in payload.get("data", [])]
        _cik_cache = {
            str(row["ticker"]).upper(): str(row["cik"]).zfill(10)
            for row in rows
            if row.get("ticker") and row.get("cik") is not None
        }
        _company_name_cache = {
            str(row["ticker"]).upper(): str(row.get("name", "")).strip()
            for row in rows
            if row.get("ticker")
        }
        _exchange_cache = {
            str(row["ticker"]).upper(): str(row.get("exchange", "")).strip()
            for row in rows
            if row.get("ticker")
        }
        return
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        pass

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(_TICKERS_URL, headers=_headers())
        response.raise_for_status()
        payload = response.json()
    _cik_cache = {
        row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in payload.values()
    }
    _company_name_cache = {
        row["ticker"].upper(): str(row.get("title", "")).strip() for row in payload.values()
    }
    _exchange_cache = {ticker: "" for ticker in _cik_cache}


async def _lookup_cik(ticker: str) -> str | None:
    await _load_company_index()
    if _cik_cache is None:
        return None
    return _cik_cache.get(ticker.upper())


async def _get_submissions(cik: str) -> dict:
    if cik not in _submissions_cache:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(_SUBMISSIONS_URL.format(cik=cik), headers=_headers())
            response.raise_for_status()
            _submissions_cache[cik] = response.json()
    return _submissions_cache[cik]


def _company_aliases(legal_name: str, former_names: list[dict]) -> tuple[str, ...]:
    names = [legal_name, *(str(item.get("name", "")).strip() for item in former_names)]
    suffixes = {
        "ag",
        "co",
        "company",
        "corp",
        "corporation",
        "inc",
        "incorporated",
        "limited",
        "llc",
        "ltd",
        "nv",
        "plc",
        "sa",
    }
    aliases: list[str] = []
    for name in names:
        normalized = " ".join(name.replace(",", " ").replace(".", " ").split())
        if not normalized:
            continue
        aliases.append(normalized)
        parts = normalized.split()
        while parts and parts[-1].casefold() in suffixes:
            parts.pop()
        if parts:
            aliases.append(" ".join(parts))
            if len(parts[0]) >= 5:
                aliases.append(parts[0])
    return tuple(dict.fromkeys(aliases))


async def get_company_name(ticker: str) -> str | None:
    """Return SEC's canonical registrant name for a ticker."""

    try:
        await _lookup_cik(ticker)
        if _company_name_cache is None:
            return None
        return _company_name_cache.get(ticker.upper()) or None
    except (httpx.HTTPError, KeyError, ValueError):
        return None


async def get_company_identity(ticker: str) -> CompanyIdentity | None:
    """Return a market-scoped issuer profile, including aliases and exchange."""

    try:
        cik = await _lookup_cik(ticker)
        if cik is None or _company_name_cache is None:
            return None
        payload = await _get_submissions(cik)
        legal_name = str(
            payload.get("name") or _company_name_cache.get(ticker.upper()) or ""
        ).strip()
        if not legal_name:
            return None
        exchanges = tuple(
            dict.fromkeys(
                value
                for value in [
                    *[str(item).strip() for item in payload.get("exchanges", [])],
                    (_exchange_cache or {}).get(ticker.upper(), ""),
                ]
                if value
            )
        )
        former_names = [
            item for item in payload.get("formerNames", []) if isinstance(item, dict)
        ]
        return CompanyIdentity(
            cik=cik,
            ticker=ticker.upper(),
            legal_name=legal_name,
            exchanges=exchanges,
            aliases=_company_aliases(legal_name, former_names),
            industry=str(payload.get("sicDescription") or "").strip() or None,
        )
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return None


def _prioritize_filings(records: list[FilingRecord], limit: int) -> list[FilingRecord]:
    """Prefer one current report of each material form, then fill by recency."""

    if limit <= 0:
        return []
    ranked = sorted(records, key=lambda item: item.filed_at or datetime.min, reverse=True)
    selected: list[FilingRecord] = []
    selected_accessions: set[str] = set()
    for form in ("10-Q", "10-K", "8-K"):
        match = next((item for item in ranked if item.form == form), None)
        if match is not None:
            selected.append(match)
            selected_accessions.add(match.accession_number)
        if len(selected) >= limit:
            return selected
    for item in ranked:
        if item.accession_number in selected_accessions:
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


async def get_filings(ticker: str, limit: int = 5) -> list[FilingRecord]:
    """Most recent filings (10-K/10-Q/8-K priority) for a ticker."""

    try:
        cik = await _lookup_cik(ticker)
        if cik is None:
            return []
        payload = await _get_submissions(cik)
        identity = await get_company_identity(ticker)

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
                    cik=cik,
                    company_name=identity.legal_name if identity else None,
                    exchange=identity.exchanges[0] if identity and identity.exchanges else None,
                    company_identity=identity,
                )
            )
        return _prioritize_filings(records, limit)
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
