"""Plain-text normalization for untrusted source content."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

_IGNORED_TAGS = {"script", "style", "noscript", "template"}
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)]\([^)]+\)")


class _PlainTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in _IGNORED_TAGS:
            self.ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _IGNORED_TAGS and self.ignored_depth:
            self.ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth:
            self.parts.append(data)


def sanitize_source_text(value: str, *, max_length: int | None = None) -> str:
    """Remove markup and normalize whitespace without preserving tag attributes or URLs."""

    parser = _PlainTextExtractor()
    try:
        parser.feed(value)
        parser.close()
        plain_text = "".join(parser.parts)
    except Exception:  # noqa: BLE001 - malformed source markup must not break analysis
        plain_text = value

    plain_text = html.unescape(plain_text).replace("\u200b", "")
    plain_text = _MARKDOWN_LINK.sub(lambda match: match.group(1), plain_text)
    normalized = " ".join(plain_text.split())
    if max_length is not None:
        return normalized[:max_length].rstrip()
    return normalized


def safe_source_snippet(content: str, title: str, *, max_length: int = 500) -> str:
    """Return a non-empty, display-safe fallback snippet from source text or title."""

    for candidate in (content, title):
        snippet = sanitize_source_text(candidate, max_length=max_length)
        if snippet:
            return snippet
    return "정제 가능한 원문이 없습니다."
