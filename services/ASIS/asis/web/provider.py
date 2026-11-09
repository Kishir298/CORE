"""
Web provider abstraction for A.S.I.S. basic web access.

The provider is the only layer allowed to touch the network. Tools depend
on the :class:`WebProvider` abstraction — never on a specific search engine
or HTTP client wiring — so the backend stays replaceable. The provider is
independent of CORE, A.S.C.S., voice, and Ollama-specific code.

Web content returned here is untrusted external data: it is passed to the
LLM as information only and must never be interpreted as instructions.
"""

from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, unquote, urlparse

if TYPE_CHECKING:  # pragma: no cover - import only for type checkers
    pass

from asis.web.extract import extract_text, extract_title, is_html_content
from asis.web.security import WebSecurityError, resolve_redirect, validate_url


def _requests():
    """Import requests lazily so base installs stay light (mirror ollama)."""
    try:
        import requests as _req

        return _req
    except ImportError as exc:
        raise WebProviderError(
            "WEB_PROVIDER_ERROR",
            "WEB_PROVIDER_ERROR: the 'requests' package is required for web "
            "access (pip install requests).",
        ) from exc

USER_AGENT = "ASIS-WebAccess/1.0 (local assistant; bounded fetch)"
SEARCH_ENDPOINT = "https://html.duckduckgo.com/html/"

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class WebProviderError(Exception):
    """Provider failure with a stable ``WEB_*`` code safe for model output."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class WebProvider(ABC):
    """Abstract web backend: search the web and fetch public pages."""

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[dict]:
        """Return up to ``max_results`` results as ``title/url/snippet/source``."""

    @abstractmethod
    def fetch(self, url: str, max_chars: int = 8000) -> dict:
        """Fetch ``url`` and return bounded readable content with metadata."""


def _source_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _unwrap_ddg_href(href: str) -> str:
    """Unwrap DuckDuckGo redirect links (``/l/?uddg=<target>``)."""
    if not href:
        return ""
    parsed = urlparse(href)
    path = parsed.path or ""
    if "uddg" in parse_qs(parsed.query):
        target = parse_qs(parsed.query)["uddg"][0]
        return unquote(target)
    if href.startswith("//"):
        return "https:" + href
    if path.startswith("/l/"):
        return ""
    return href


class _DuckResultsParser(HTMLParser):
    """Tolerant parser for the DuckDuckGo HTML endpoint result page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict] = []
        self._in_title_link = False
        self._in_snippet = False
        self._current: dict | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        classes = dict(attrs).get("class", "")
        names = set(classes.split())
        if tag == "a" and "result__a" in names:
            href = _unwrap_ddg_href(dict(attrs).get("href", ""))
            if self._current is not None:
                self._finish_current()
            self._current = {"title": "", "url": href, "snippet": ""}
            self._in_title_link = True
            self._text = []
        elif self._current is not None and (
            (tag == "a" and "result__snippet" in names)
            or (tag == "td" and "result-snippet" in names)
        ):
            self._in_snippet = True
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_title_link and self._current is not None:
            self._current["title"] = " ".join("".join(self._text).split())
            self._in_title_link = False
            self._text = []
        elif tag in ("a", "td") and self._in_snippet and self._current is not None:
            snippet = " ".join("".join(self._text).split())
            if snippet and not self._current["snippet"]:
                self._current["snippet"] = snippet
            self._in_snippet = False
            self._text = []
            self._finish_current()

    def handle_data(self, data: str) -> None:
        if self._in_title_link or self._in_snippet:
            self._text.append(data)

    def _finish_current(self) -> None:
        current, self._current = self._current, None
        if current is None:
            return
        url = (current.get("url") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
            return
        current["url"] = url
        current["source"] = _source_of(url)
        self.results.append(current)

    def finish(self) -> None:
        """Flush any trailing result (e.g. entries without a snippet)."""
        if self._in_title_link and self._current is not None:
            self._current["title"] = " ".join("".join(self._text).split())
            self._in_title_link = False
            self._text = []
        self._finish_current()


def parse_ddg_results(markup: str, *, max_results: int = 5) -> list[dict]:
    """Parse a DuckDuckGo HTML result page into bounded result dicts."""
    parser = _DuckResultsParser()
    try:
        parser.feed(markup or "")
        parser.finish()
    except Exception:
        raise WebProviderError(
            "WEB_PARSE_ERROR", "WEB_PARSE_ERROR: search response could not be read."
        ) from None
    return parser.results[: max(0, max_results)]


class DuckDuckGoWebProvider(WebProvider):
    """HTTP-only search (DuckDuckGo HTML endpoint) + bounded page fetch.

    No browser automation, no JavaScript, no credentials. All URLs —
    initial and every redirect hop — pass SSRF validation before connecting.
    """

    def __init__(
        self,
        *,
        timeout: int = 10,
        max_response_bytes: int = 1_000_000,
        max_redirects: int = 3,
        session: Any | None = None,
    ) -> None:
        self._timeout = timeout
        self._max_response_bytes = max_response_bytes
        self._max_redirects = max_redirects
        self._session = session

    def _client(self) -> Any:
        if self._session is not None:
            return self._session
        requests = _requests()
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})
        return session

    # -- search ---------------------------------------------------------
    def search(self, query: str, max_results: int = 5) -> list[dict]:
        if not isinstance(query, str) or not query.strip():
            raise WebProviderError(
                "WEB_PROVIDER_ERROR", "WEB_PROVIDER_ERROR: query must be non-empty."
            )
        count = max(1, min(int(max_results), 10))
        client = self._client()
        try:
            response = client.get(
                SEARCH_ENDPOINT,
                params={"q": query.strip()},
                headers={"User-Agent": USER_AGENT},
                timeout=self._timeout,
            )
            response.raise_for_status()
            markup = response.text
        except _requests().Timeout:
            raise WebProviderError(
                "WEB_TIMEOUT", "WEB_TIMEOUT: search request timed out."
            ) from None
        except _requests().ConnectionError:
            raise WebProviderError(
                "WEB_UNAVAILABLE", "WEB_UNAVAILABLE: search service unreachable."
            ) from None
        except _requests().HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", "?")
            raise WebProviderError(
                "WEB_HTTP_ERROR",
                f"WEB_HTTP_ERROR: search failed (status {status}).",
            ) from None
        except _requests().RequestException:
            raise WebProviderError(
                "WEB_PROVIDER_ERROR", "WEB_PROVIDER_ERROR: search request failed."
            ) from None
        return parse_ddg_results(markup, max_results=count)

    # -- fetch ----------------------------------------------------------
    def fetch(self, url: str, max_chars: int = 8000) -> dict:
        try:
            validated = validate_url(url)
            current = validated.url
        except WebSecurityError as exc:
            raise WebProviderError(exc.code, exc.message) from None
        client = self._client()
        redirects_followed = 0
        try:
            while True:
                try:
                    response = client.get(
                        current,
                        headers={"User-Agent": USER_AGENT},
                        timeout=self._timeout,
                        allow_redirects=False,
                        stream=True,
                    )
                except _requests().Timeout:
                    raise WebProviderError(
                        "WEB_TIMEOUT", "WEB_TIMEOUT: page request timed out."
                    ) from None
                except _requests().ConnectionError:
                    raise WebProviderError(
                        "WEB_UNAVAILABLE", "WEB_UNAVAILABLE: page unreachable."
                    ) from None
                except _requests().RequestException:
                    raise WebProviderError(
                        "WEB_PROVIDER_ERROR",
                        "WEB_PROVIDER_ERROR: page request failed.",
                    ) from None
                if response.status_code in _REDIRECT_STATUSES:
                    if redirects_followed >= self._max_redirects:
                        raise WebProviderError(
                            "WEB_HTTP_ERROR",
                            "WEB_HTTP_ERROR: too many redirects.",
                        )
                    location = response.headers.get("Location", "")
                    try:
                        nxt = resolve_redirect(current, location)
                        validated = validate_url(nxt)
                    except WebSecurityError as exc:
                        raise WebProviderError(exc.code, exc.message) from None
                    redirects_followed += 1
                    current = validated.url
                    with contextlib.suppress(Exception):
                        response.close()
                    continue
                return self._read_response(
                    response, original_url=url.strip(), max_chars=max_chars
                )
        finally:
            if self._session is None:
                with contextlib.suppress(Exception):
                    client.close()

    def _read_response(
        self, response: Any, *, original_url: str, max_chars: int
    ) -> dict:
        status = response.status_code
        final_url = getattr(response, "url", original_url)
        content_type = response.headers.get("Content-Type", "")
        if status >= 400:
            with contextlib.suppress(Exception):
                response.close()
            raise WebProviderError(
                "WEB_HTTP_ERROR", f"WEB_HTTP_ERROR: page failed (status {status})."
            )
        limit = self._max_response_bytes + 1
        chunks: list[bytes] = []
        received = 0
        try:
            for piece in response.iter_content(chunk_size=65536):
                if not piece:
                    continue
                received += len(piece)
                if received > limit:
                    raise WebProviderError(
                        "WEB_RESPONSE_TOO_LARGE",
                        "WEB_RESPONSE_TOO_LARGE: page exceeds the download limit.",
                    )
                chunks.append(piece)
        except WebProviderError:
            raise
        except Exception:
            raise WebProviderError(
                "WEB_PROVIDER_ERROR", "WEB_PROVIDER_ERROR: page read failed."
            ) from None
        finally:
            with contextlib.suppress(Exception):
                response.close()
        raw = b"".join(chunks)
        encoding = getattr(response, "encoding", None) or "utf-8"
        try:
            markup = raw.decode(encoding, errors="replace")
        except (LookupError, ValueError):
            markup = raw.decode("utf-8", errors="replace")
        if is_html_content(content_type):
            title = extract_title(markup)
            text, truncated = extract_text(markup, max_chars=max_chars)
        elif content_type.split(";")[0].strip().lower().startswith("text/"):
            title = ""
            text = markup
            truncated = False
            if len(text) > max_chars:
                text, truncated = text[:max_chars], True
        else:
            title, text, truncated = "", "", False
        return {
            "url": original_url,
            "final_url": final_url,
            "status_code": status,
            "content_type": content_type,
            "title": title,
            "text": text,
            "truncated": truncated,
        }


def build_default_provider(settings_obj=None) -> WebProvider:
    """Build the configured provider from ``settings.web`` (no credentials)."""
    if settings_obj is None:
        from asis.configuration.settings import settings as settings_obj
    web = settings_obj.web
    if not web.enabled:
        return _OfflineWebProvider()
    return DuckDuckGoWebProvider(
        timeout=web.timeout,
        max_response_bytes=web.max_response_bytes,
        max_redirects=web.max_redirects,
    )


class _OfflineWebProvider(WebProvider):
    """Offline fallback: returns empty results without network calls."""

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        return []

    def fetch(self, url: str, max_chars: int = 8000) -> dict:
        return {
            "url": url,
            "final_url": url,
            "status_code": 0,
            "content_type": "",
            "title": "",
            "text": "[Web access disabled - running offline]",
            "truncated": False,
        }
