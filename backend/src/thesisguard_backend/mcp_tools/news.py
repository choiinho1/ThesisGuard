"""News source — Google News RSS (no API key required).

Note: the original TDD's MCP Tool table (SEC / Market / Macro / Portfolio)
never defined a News source, even though `ResearchTools.get_news()` and the
"News Agent" node both need one. This module fills that gap.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from agents.sanitization import sanitize_source_text

_RSS_URL = "https://news.google.com/rss/search"


@dataclass(slots=True)
class NewsItem:
    title: str
    url: str
    published_at: datetime | None
    source: str
    summary: str


async def get_news(query: str, limit: int = 5) -> list[NewsItem]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                _RSS_URL, params={"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
            )
            response.raise_for_status()
            root = ElementTree.fromstring(response.text)

        items: list[NewsItem] = []
        for item in root.findall("./channel/item")[:limit]:
            title = sanitize_source_text(item.findtext("title") or "")
            link = (item.findtext("link") or "").strip()
            pub_date = item.findtext("pubDate")
            source = sanitize_source_text(item.findtext("source") or "") or "Google News"
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
                        source=source,
                        summary=description,
                    )
                )
        return items
    except (httpx.HTTPError, ElementTree.ParseError):
        return []
