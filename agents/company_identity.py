"""Deterministic issuer identity checks for retrieved source documents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

from agents.models import EvidenceSourceType, SourceDocument
from agents.sanitization import sanitize_source_text

_LEGAL_SUFFIXES = {
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
_AMBIGUOUS_SINGLE_NAME_TOKENS = {
    "all",
    "alphabet",
    "apple",
    "block",
    "first",
    "general",
    "global",
    "meta",
    "national",
    "on",
    "target",
    "unity",
    "united",
}
_AMBIGUOUS_TICKERS = {
    "A",
    "AI",
    "ALL",
    "ARE",
    "CAR",
    "CAT",
    "FOR",
    "IT",
    "ON",
    "OR",
    "SO",
    "T",
    "U",
}
_MARKET_CONTEXT = {
    "analyst",
    "earnings",
    "exchange",
    "guidance",
    "investor",
    "nasdaq",
    "nyse",
    "revenue",
    "shares",
    "stock",
    "실적",
    "주가",
    "주식",
    "매출",
}
_TOKEN = re.compile(r"[0-9A-Za-z가-힣]{2,}")


class CompanyMatchStatus(StrEnum):
    MATCH = "MATCH"
    AMBIGUOUS = "AMBIGUOUS"
    MISMATCH = "MISMATCH"


@dataclass(frozen=True, slots=True)
class CompanyIdentityResolution:
    status: CompanyMatchStatus
    confidence: float
    signals: tuple[str, ...]

    def as_metadata(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "confidence": self.confidence,
            "signals": list(self.signals),
        }


def _normalized_phrase(value: str) -> str:
    return " ".join(_TOKEN.findall(sanitize_source_text(value).casefold()))


def _tokens(value: str) -> set[str]:
    return set(_TOKEN.findall(sanitize_source_text(value).casefold()))


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [item for item in value if isinstance(item, str)]
    return []


def _identity_metadata(document: SourceDocument) -> dict[str, object]:
    nested = document.metadata.get("company_identity", {})
    return nested if isinstance(nested, dict) else {}


def _name_aliases(document: SourceDocument) -> list[str]:
    identity = _identity_metadata(document)
    legal_name = str(identity.get("legal_name") or document.metadata.get("company_name") or "")
    aliases = [
        legal_name,
        *_string_list(identity.get("aliases")),
        *_string_list(document.metadata.get("company_aliases")),
    ]
    normalized: list[str] = []
    for alias in aliases:
        phrase = _normalized_phrase(alias)
        if not phrase:
            continue
        normalized.append(phrase)
        parts = phrase.split()
        while parts and parts[-1] in _LEGAL_SUFFIXES:
            parts.pop()
        if parts:
            normalized.append(" ".join(parts))
            if len(parts[0]) >= 5:
                normalized.append(parts[0])
    return list(dict.fromkeys(normalized))


def _anchor_phrases(document: SourceDocument) -> list[str]:
    identity = _identity_metadata(document)
    values = [
        *_string_list(identity.get("industry")),
        *_string_list(identity.get("products")),
        *_string_list(identity.get("executives")),
        *_string_list(identity.get("context_terms")),
        *_string_list(document.metadata.get("company_context_terms")),
    ]
    return list(
        dict.fromkeys(phrase for value in values if (phrase := _normalized_phrase(value)))
    )


def _official_domain_match(document: SourceDocument) -> bool:
    if document.source_url is None:
        return False
    identity = _identity_metadata(document)
    domains = {
        domain.casefold().removeprefix("www.")
        for domain in _string_list(identity.get("official_domains"))
        if domain
    }
    if not domains:
        return False
    hostname = (urlsplit(str(document.source_url)).hostname or "").casefold().removeprefix("www.")
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in domains)


def _qualified_ticker_match(text: str, ticker: str) -> bool:
    escaped = re.escape(ticker)
    patterns = (
        rf"\${escaped}(?![A-Z0-9])",
        rf"\b(?:NASDAQ|NYSE|AMEX)\s*:\s*{escaped}\b",
        rf"\b(?:ticker|symbol)\s+(?:is\s+)?{escaped}\b",
        rf"\({escaped}\)",
    )
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _plain_ticker_match(text: str, ticker: str) -> bool:
    if ticker.upper() in _AMBIGUOUS_TICKERS:
        return False
    return re.search(rf"(?<![A-Z0-9]){re.escape(ticker.upper())}(?![A-Z0-9])", text) is not None


def identity_embedding_prefix(document: SourceDocument) -> str:
    """Return canonical issuer fields that should travel with RAG chunks."""

    identity = _identity_metadata(document)
    if not identity:
        return ""
    values = {
        "identifier_scheme": identity.get("identifier_scheme"),
        "identifier": identity.get("identifier"),
        "ticker": identity.get("ticker"),
        "exchange": ",".join(_string_list(identity.get("exchanges"))),
        "legal_name": identity.get("legal_name"),
    }
    fields = [f"{key}={value}" for key, value in values.items() if value]
    return "issuer_identity " + " ".join(fields) if fields else ""


def resolve_company_identity(
    document: SourceDocument,
    *,
    ticker: str,
) -> CompanyIdentityResolution:
    """Classify a document as matching, ambiguous, or mismatching the requested issuer."""

    if document.source_type != EvidenceSourceType.NEWS:
        return CompanyIdentityResolution(
            CompanyMatchStatus.MATCH,
            1.0,
            ("issuer_scoped_source",),
        )

    raw_text = f"{document.title}\n{document.content[:4000]}"
    normalized_text = _normalized_phrase(raw_text)
    text_tokens = _tokens(raw_text)
    signals: list[str] = []

    qualified_ticker = _qualified_ticker_match(raw_text, ticker)
    plain_ticker = _plain_ticker_match(raw_text, ticker)
    if qualified_ticker:
        signals.append("qualified_ticker")
    elif plain_ticker:
        signals.append("plain_ticker")

    if _official_domain_match(document):
        signals.append("official_domain")

    aliases = _name_aliases(document)
    matched_aliases = [
        alias
        for alias in aliases
        if re.search(rf"(?:^|\s){re.escape(alias)}(?:$|\s)", normalized_text)
    ]
    strong_name = False
    weak_name = False
    if matched_aliases:
        best_alias = max(matched_aliases, key=lambda value: (len(value.split()), len(value)))
        parts = best_alias.split()
        strong_name = len(parts) >= 2 or (
            len(parts[0]) >= 7 and parts[0] not in _AMBIGUOUS_SINGLE_NAME_TOKENS
        )
        weak_name = not strong_name
        signals.append("strong_name" if strong_name else "weak_name")

    anchors = _anchor_phrases(document)
    anchor_match = any(
        re.search(rf"(?:^|\s){re.escape(anchor)}(?:$|\s)", normalized_text)
        for anchor in anchors
    )
    if anchor_match:
        signals.append("company_context")
    market_context = bool(text_tokens & _MARKET_CONTEXT)
    if market_context:
        signals.append("market_context")

    if "official_domain" in signals or qualified_ticker or strong_name:
        return CompanyIdentityResolution(CompanyMatchStatus.MATCH, 0.95, tuple(signals))
    if plain_ticker:
        return CompanyIdentityResolution(CompanyMatchStatus.MATCH, 0.85, tuple(signals))
    if weak_name and (plain_ticker or anchor_match or market_context):
        return CompanyIdentityResolution(CompanyMatchStatus.MATCH, 0.8, tuple(signals))
    if weak_name or anchor_match:
        return CompanyIdentityResolution(CompanyMatchStatus.AMBIGUOUS, 0.4, tuple(signals))
    return CompanyIdentityResolution(CompanyMatchStatus.MISMATCH, 0.0, tuple(signals))
