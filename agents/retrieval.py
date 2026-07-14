"""Deterministic research preselection and document compaction helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from agents.models import EvidenceSourceType, SourceDocument, StructuredThesis
from agents.sanitization import sanitize_source_text
from agents.state import ResearchData

_TOKEN = re.compile(r"[0-9A-Za-z가-힣]{2,}")
_TRACKING_QUERY_PREFIXES = ("utm_", "fbclid", "gclid")
_MACRO_TERMS = {
    "cpi",
    "inflation",
    "interest",
    "rate",
    "rates",
    "treasury",
    "yield",
}
_MACRO_KOREAN_STEMS = ("금리", "국채", "물가", "인플레이션", "환율")
_GENERIC_COMPANY_TOKENS = {
    "co",
    "company",
    "corp",
    "corporation",
    "group",
    "holding",
    "holdings",
    "inc",
    "incorporated",
    "limited",
    "ltd",
    "markets",
    "plc",
}


def _tokens(values: Iterable[str]) -> set[str]:
    return {
        token.casefold()
        for value in values
        for token in _TOKEN.findall(sanitize_source_text(value))
    }


def thesis_search_terms(thesis: StructuredThesis, focus_points: Sequence[str]) -> list[str]:
    """Return the thesis claims that should guide retrieval without an extra model call."""

    return list(
        dict.fromkeys(
            [
                *focus_points,
                thesis.main_thesis,
                *thesis.key_assumptions,
                *thesis.positive_signals,
                *thesis.negative_signals,
                *thesis.key_risks,
            ]
        )
    )


def _canonical_url(document: SourceDocument) -> str:
    if document.source_url is None:
        return ""
    parts = urlsplit(str(document.source_url))
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if not key.casefold().startswith(_TRACKING_QUERY_PREFIXES)
        )
    )
    return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), parts.path, query, ""))


def _title_key(document: SourceDocument) -> str:
    title = sanitize_source_text(document.title).casefold()
    source = sanitize_source_text(str(document.metadata.get("source", ""))).casefold()
    if source and title.endswith(f" - {source}"):
        title = title[: -(len(source) + 3)]
    return " ".join(_TOKEN.findall(title))


def _freshness_score(document: SourceDocument, *, now: datetime, lookback_days: int) -> float:
    if document.published_at is None:
        return 0.0
    published_at = document.published_at
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    age = max(timedelta(0), now - published_at.astimezone(UTC))
    return max(0.0, 1 - (age.days / lookback_days))


def _published_at(document: SourceDocument) -> datetime:
    if document.published_at is None:
        return datetime.min.replace(tzinfo=UTC)
    if document.published_at.tzinfo is None:
        return document.published_at.replace(tzinfo=UTC)
    return document.published_at.astimezone(UTC)


def _company_identity_tokens(document: SourceDocument) -> set[str]:
    company_name = str(document.metadata.get("company_name", ""))
    return _tokens([company_name]) - _GENERIC_COMPANY_TOKENS


def _selection_score(
    document: SourceDocument,
    *,
    ticker: str,
    query_tokens: set[str],
    now: datetime,
    lookback_days: int,
) -> float:
    title_tokens = _tokens([document.title])
    body_tokens = _tokens([document.content[:4000]])
    document_tokens = title_tokens | body_tokens
    overlap = len(query_tokens & document_tokens) / max(1, min(len(query_tokens), 12))
    ticker_match = ticker.casefold() in document_tokens
    company_match = bool(_company_identity_tokens(document) & document_tokens)
    source_base = {
        EvidenceSourceType.SEC_FILING: 0.45,
        EvidenceSourceType.IR: 0.45,
        EvidenceSourceType.EARNINGS: 0.45,
        EvidenceSourceType.NEWS: 0.10,
        EvidenceSourceType.MACRO: 0.05,
    }[document.source_type]
    score = source_base + min(0.35, overlap * 1.5)
    if ticker_match:
        score += 0.15
    if company_match:
        score += 0.25
    if document.source_type == EvidenceSourceType.NEWS:
        score += 0.15 * _freshness_score(document, now=now, lookback_days=lookback_days)
    return min(1.0, score)


def preselect_documents(
    research_data: ResearchData,
    *,
    ticker: str,
    thesis: StructuredThesis,
    focus_points: Sequence[str],
    lookback_days: int,
    min_news_score: float,
    source_limits: dict[str, int],
    now: datetime | None = None,
) -> list[SourceDocument]:
    """Remove stale/duplicate candidates and retain a diverse, ranked source set."""

    now = (now or datetime.now(UTC)).astimezone(UTC)
    search_terms = thesis_search_terms(thesis, focus_points)
    query_tokens = _tokens([ticker, *search_terms])
    search_text = sanitize_source_text(" ".join(search_terms)).casefold()
    macro_relevant = bool(query_tokens & _MACRO_TERMS) or any(
        stem in search_text for stem in _MACRO_KOREAN_STEMS
    )
    cutoff = now - timedelta(days=lookback_days)
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    candidates: dict[str, list[tuple[float, SourceDocument]]] = {
        "filings": [],
        "news": [],
        "macro": [],
    }

    for key in ("filings", "news", "macro"):
        for document in sorted(research_data[key], key=_published_at, reverse=True):
            if not sanitize_source_text(document.title) or not sanitize_source_text(
                document.content
            ):
                continue
            if key == "macro" and not macro_relevant:
                continue
            if key == "news" and document.published_at is not None:
                published_at = document.published_at
                if published_at.tzinfo is None:
                    published_at = published_at.replace(tzinfo=UTC)
                if published_at.astimezone(UTC) < cutoff:
                    continue
            if key == "news":
                identity_tokens = _company_identity_tokens(document)
                document_tokens = _tokens([document.title, document.content[:4000]])
                if identity_tokens and not identity_tokens & document_tokens:
                    continue

            canonical_url = _canonical_url(document)
            title_key = _title_key(document)
            duplicate = (
                document.document_id in seen_ids
                or bool(canonical_url and canonical_url in seen_urls)
                or bool(len(title_key) >= 20 and title_key in seen_titles)
            )
            if duplicate:
                continue
            seen_ids.add(document.document_id)
            if canonical_url:
                seen_urls.add(canonical_url)
            if len(title_key) >= 20:
                seen_titles.add(title_key)

            score = _selection_score(
                document,
                ticker=ticker,
                query_tokens=query_tokens,
                now=now,
                lookback_days=lookback_days,
            )
            if key == "news" and score < min_news_score:
                continue
            metadata = {**document.metadata, "selection_score": round(score, 4)}
            candidates[key].append((score, document.model_copy(update={"metadata": metadata})))

    selected: list[SourceDocument] = []
    for key in ("filings", "news", "macro"):
        ranked = sorted(
            candidates[key],
            key=lambda item: (
                item[0],
                item[1].published_at or datetime.min.replace(tzinfo=UTC),
                item[1].document_id,
            ),
            reverse=True,
        )
        selected.extend(document for _, document in ranked[: source_limits[key]])
    return selected


def limit_documents_by_source(
    documents: Sequence[SourceDocument], source_limits: dict[str, int]
) -> list[SourceDocument]:
    """Apply final per-source document caps while preserving ranking order."""

    source_keys = {
        EvidenceSourceType.SEC_FILING: "filings",
        EvidenceSourceType.IR: "filings",
        EvidenceSourceType.EARNINGS: "filings",
        EvidenceSourceType.NEWS: "news",
        EvidenceSourceType.MACRO: "macro",
    }
    counts = {key: 0 for key in source_limits}
    selected: list[SourceDocument] = []
    for document in documents:
        key = source_keys[document.source_type]
        if counts[key] >= source_limits[key]:
            continue
        selected.append(document)
        counts[key] += 1
    return selected


def _passage_chunks(content: str, *, chunk_chars: int = 1200) -> list[str]:
    blocks = [" ".join(block.split()) for block in content.splitlines() if block.strip()]
    if len(blocks) <= 1:
        blocks = [part.strip() for part in re.split(r"(?<=[.!?])\s+", content) if part.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for block in blocks:
        if current and current_length + len(block) + 1 > chunk_chars:
            chunks.append(" ".join(current))
            current = []
            current_length = 0
        current.append(block)
        current_length += len(block) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


def extract_relevant_passages(
    content: str,
    search_terms: Sequence[str],
    *,
    max_chars: int = 6000,
) -> str:
    """Keep the highest-overlap filing passages before sending them to the LLM."""

    chunks = _passage_chunks(content)
    if not chunks:
        return sanitize_source_text(content, max_length=max_chars)
    query_tokens = _tokens(search_terms)
    scored = [
        (len(query_tokens & _tokens([chunk])), index, chunk) for index, chunk in enumerate(chunks)
    ]
    matching = [item for item in scored if item[0] > 0]
    if not matching:
        return " ".join(chunks)[:max_chars].rstrip()

    chosen: list[tuple[int, str]] = []
    length = 0
    for _, index, chunk in sorted(matching, key=lambda item: (item[0], -item[1]), reverse=True):
        if chosen and length + len(chunk) + 1 > max_chars:
            continue
        chosen.append((index, chunk))
        length += len(chunk) + 1
        if length >= max_chars:
            break
    return "\n".join(chunk for _, chunk in sorted(chosen))[:max_chars].rstrip()
