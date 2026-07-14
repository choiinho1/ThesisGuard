"""News RSS retrieval with rich summaries and direct publisher links."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, urlsplit
from xml.etree import ElementTree

import httpx
from agents.sanitization import sanitize_source_text

_BING_RSS_URL = "https://www.bing.com/news/search"
_GOOGLE_RSS_URL = "https://news.google.com/rss/search"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


@dataclass(slots=True)
class NewsItem:
    title: str
    url: str
    published_at: datetime | None
    source: str
    summary: str


def _publisher_url(value: str) -> str:
    """Resolve Bing's RSS click wrapper to the publisher URL when available."""

    parsed = urlsplit(value)
    if parsed.netloc.casefold().endswith("bing.com"):
        target = parse_qs(parsed.query).get("url", [])
        if target and target[0].startswith(("http://", "https://")):
            return target[0]
    return value


def _source_name(item: ElementTree.Element) -> str:
    for child in item:
        if child.tag.casefold().endswith("source"):
            source = sanitize_source_text(child.text or "")
            if source:
                return source
    return "News RSS"


def _parse_items(xml: str, limit: int) -> list[NewsItem]:
    root = ElementTree.fromstring(xml)
    items: list[NewsItem] = []
    for item in root.findall("./channel/item")[:limit]:
        title = sanitize_source_text(item.findtext("title") or "")
        link = _publisher_url((item.findtext("link") or "").strip())
        pub_date = item.findtext("pubDate")
        description = sanitize_source_text(item.findtext("description") or "")
        published_at = None
        if pub_date:
            try:
                published_at = parsedate_to_datetime(pub_date)
            except (TypeError, ValueError):
                published_at = None
        if title and link:
            items.append(
                NewsItem(
                    title=title,
                    url=link,
                    published_at=published_at,
                    source=_source_name(item),
                    summary=description,
                )
            )
    return items


async def get_news(query: str, limit: int = 5) -> list[NewsItem]:
    """Fetch richer Bing RSS summaries, with Google News as a fallback."""

    try:
        async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
            response = await client.get(
                _BING_RSS_URL,
                params={"q": query, "format": "rss", "setlang": "ko-kr"},
            )
            response.raise_for_status()
            items = _parse_items(response.text, limit)
            if items:
                return items

            response = await client.get(
                _GOOGLE_RSS_URL,
                params={"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"},
            )
            response.raise_for_status()
            return _parse_items(response.text, limit)
    except (httpx.HTTPError, ElementTree.ParseError):
        return []
