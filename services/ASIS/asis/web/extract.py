"""
Readable-text extraction for A.S.I.S. basic web access.

Standard-library only (``html.parser``): strips scripts, styles, and tags,
unescapes entities, and collapses whitespace. Never executes JavaScript
or any downloaded code — output is plain text treated as untrusted data.
"""

from __future__ import annotations

import html as _html
import re
from html.parser import HTMLParser

_SKIP_TAGS = frozenset({"script", "style", "noscript", "template"})
_WHITESPACE = re.compile(r"\s+")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._chunks: list[str] = []
        self._skip_depth = 0
        self._head_depth = 0
        self.title = ""

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "head":
            self._head_depth += 1
            return
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in ("br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "head" and self._head_depth > 0:
            self._head_depth -= 1
        elif tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0 or self._head_depth > 0:
            return
        text = data.strip()
        if text:
            self._chunks.append(text + " ")

    def handle_comment(self, data: str) -> None:
        return

    def text(self) -> str:
        raw = "".join(self._chunks)
        collapsed = _WHITESPACE.sub(" ", raw)
        # Restore paragraph breaks where block tags emitted newlines.
        lines = [line.strip() for line in raw.split("\n")]
        cleaned = "\n".join(line for line in lines if line)
        if cleaned:
            return _html.unescape(_WHITESPACE.sub(" ", cleaned).replace(" \n", "\n"))
        return _html.unescape(collapsed.strip())


class _TitleExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_title = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._parts.append(data.strip())

    @property
    def title(self) -> str:
        return _html.unescape(" ".join(part for part in self._parts if part)).strip()


def extract_title(markup: str) -> str:
    """Return the document ``<title>`` text, or ``""`` when absent."""
    if not isinstance(markup, str) or not markup:
        return ""
    parser = _TitleExtractor()
    try:
        parser.feed(markup[:200_000])
    except Exception:
        return ""
    return parser.title[:500]


def extract_text(markup: str, *, max_chars: int = 8000) -> tuple[str, bool]:
    """Extract readable text from HTML ``markup``.

    Returns ``(text, truncated)`` where ``truncated`` is True when the
    output was cut to ``max_chars`` characters.
    """
    if not isinstance(markup, str) or not markup.strip():
        return "", False
    parser = _TextExtractor()
    try:
        parser.feed(markup[:2_000_000])
    except Exception:
        return "", False
    text = parser.text()
    if len(text) > max_chars:
        return text[:max_chars], True
    return text, False


def is_html_content(content_type: str | None) -> bool:
    """Return True when a Content-Type header denotes HTML."""
    if not content_type:
        return False
    return "html" in content_type.split(";")[0].lower()
