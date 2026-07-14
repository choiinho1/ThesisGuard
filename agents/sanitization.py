"""Plain-text normalization for untrusted source content."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

_IGNORED_TAGS = {"script", "style", "noscript", "template"}
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)]\([^)]+\)")
_HANGUL = re.compile(r"[가-힣]")


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


def is_korean_text(value: str) -> bool:
    """Return whether display text contains at least one Hangul syllable."""

    return bool(_HANGUL.search(value))


def normalize_korean_summary(
    value: str,
    *,
    fallback: str = "한글 근거 요약을 생성하지 못했습니다.",
) -> str:
    """Normalize a Korean evidence summary to the public 500-character limit."""

    summary = sanitize_source_text(value, max_length=500)
    return summary if summary and is_korean_text(summary) else fallback


def split_source_passages(
    value: str,
    *,
    max_chars: int = 500,
    max_passages: int = 20,
) -> list[str]:
    """Split normalized source text into numbered passages selected by the model."""

    text = sanitize_source_text(value)
    if not text:
        return []
    sentences = [part.strip() for part in re.split(r"(?<=[.!?。])\s+", text) if part.strip()]
    passages: list[str] = []
    current: list[str] = []
    current_length = 0

    def flush() -> None:
        nonlocal current, current_length
        if current:
            passages.append(" ".join(current))
            current = []
            current_length = 0

    for sentence in sentences:
        pieces = [sentence]
        if len(sentence) > max_chars:
            words = sentence.split()
            pieces = []
            part: list[str] = []
            part_length = 0
            for word in words:
                if part and part_length + len(word) + 1 > max_chars:
                    pieces.append(" ".join(part))
                    part = []
                    part_length = 0
                if len(word) > max_chars:
                    if part:
                        pieces.append(" ".join(part))
                        part = []
                        part_length = 0
                    pieces.extend(
                        word[index : index + max_chars] for index in range(0, len(word), max_chars)
                    )
                    continue
                part.append(word)
                part_length += len(word) + 1
            if part:
                pieces.append(" ".join(part))

        for piece in pieces:
            if current and current_length + len(piece) + 1 > max_chars:
                flush()
            current.append(piece)
            current_length += len(piece) + 1
            if len(passages) >= max_passages:
                return passages[:max_passages]
    flush()
    return passages[:max_passages]
