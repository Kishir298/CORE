"""
Basic web access tools for A.S.I.S.: ``web_search`` and ``web_fetch``.

Both tools run through the standard path (ToolRegistry -> ToolRouter ->
PermissionManager/authorizer -> ToolExecutor) like every other tool. They
depend on the :class:`asis.web.provider.WebProvider` abstraction — never on
a specific search engine — and perform no network access themselves.

Retrieved web content is untrusted external data returned as information
for the model to interpret. It is never executed, never written to memory
automatically, and never allowed to bypass permissions. Web access is
optional: when ``ASIS_WEB_ENABLED=false`` both tools fail cleanly with
``WEB_DISABLED`` and the rest of A.S.I.S. keeps working.
"""

from __future__ import annotations

from typing import Any

from asis.permissions.models import PermissionLevel

from ..base import Tool, ToolMetadata
from ..result import ToolResult


def _web_settings():
    from asis.configuration.settings import settings

    return settings.web


def _disabled_result(tool_name: str) -> ToolResult:
    return ToolResult.failure(
        error="WEB_DISABLED: web access is disabled by configuration.",
        tool_name=tool_name,
    )


class WebSearchTool(Tool):
    """Search the web and return bounded structured results."""

    metadata = ToolMetadata(
        name="web_search",
        description=(
            "Search the web for information. Returns short structured "
            "results (title, url, snippet, source)."
        ),
        category="web",
        permission=PermissionLevel.LOW,
        tags=("web", "search", "network"),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["query"],
        },
    )

    def __init__(self, provider=None) -> None:
        self._provider = provider

    def _client(self):
        if self._provider is not None:
            return self._provider
        from asis.web.provider import build_default_provider

        return build_default_provider()

    def execute(self, **kwargs: Any) -> ToolResult:
        web = _web_settings()
        if not web.enabled:
            return _disabled_result(self.name)
        query = kwargs.get("query", "")
        if not isinstance(query, str) or not query.strip():
            return ToolResult.failure(
                error="'query' must be a non-empty string.",
                tool_name=self.name,
            )
        if len(query.strip()) > web.max_query_length:
            return ToolResult.failure(
                error="'query' exceeds the maximum permitted length.",
                tool_name=self.name,
            )
        raw_count = kwargs.get("max_results", web.max_results)
        if isinstance(raw_count, bool) or not isinstance(raw_count, int):
            return ToolResult.failure(
                error="'max_results' must be an integer.",
                tool_name=self.name,
            )
        count = max(1, min(raw_count, web.max_results))
        try:
            results = self._client().search(query.strip(), count)
        except Exception as exc:  # provider already maps to WEB_* codes
            code = getattr(exc, "code", None)
            message = getattr(exc, "message", None) or str(exc) or "search failed."
            if code:
                return ToolResult.failure(
                    error=f"{code}: {message.split(': ', 1)[-1]}"
                    if ": " in message
                    else f"{code}: {message}",
                    tool_name=self.name,
                )
            return ToolResult.failure(
                error=f"WEB_PROVIDER_ERROR: {message}",
                tool_name=self.name,
            )
        bounded = list(results or [])[:count]
        return ToolResult.ok(
            data={"query": query.strip(), "results": bounded},
            tool_name=self.name,
        )


class WebFetchTool(Tool):
    """Fetch readable content from a public HTTP/HTTPS page."""

    metadata = ToolMetadata(
        name="web_fetch",
        description=(
            "Fetch readable content from a public HTTP(S) webpage. "
            "Returns bounded text plus page metadata."
        ),
        category="web",
        permission=PermissionLevel.LOW,
        tags=("web", "fetch", "network"),
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "max_chars": {"type": "integer"},
            },
            "required": ["url"],
        },
    )

    def __init__(self, provider=None) -> None:
        self._provider = provider

    def _client(self):
        if self._provider is not None:
            return self._provider
        from asis.web.provider import build_default_provider

        return build_default_provider()

    def execute(self, **kwargs: Any) -> ToolResult:
        web = _web_settings()
        if not web.enabled:
            return _disabled_result(self.name)
        url = kwargs.get("url", "")
        if not isinstance(url, str) or not url.strip():
            return ToolResult.failure(
                error="'url' must be a non-empty string.",
                tool_name=self.name,
            )
        if len(url.strip()) > web.max_url_length:
            return ToolResult.failure(
                error="'url' exceeds the maximum permitted length.",
                tool_name=self.name,
            )
        # Lightweight scheme pre-check (full SSRF validation, including DNS
        # resolution and redirect revalidation, happens in the provider).
        from urllib.parse import urlparse as _urlparse

        _parsed = _urlparse(url.strip())
        _scheme = (_parsed.scheme or "").lower()
        if _scheme not in ("http", "https"):
            if not _scheme or not _parsed.hostname:
                return ToolResult.failure(
                    error="WEB_INVALID_URL: 'url' must be a valid http(s) URL.",
                    tool_name=self.name,
                )
            return ToolResult.failure(
                error="WEB_UNSUPPORTED_SCHEME: only http and https URLs "
                "are permitted.",
                tool_name=self.name,
            )
        raw_chars = kwargs.get("max_chars", web.max_chars)
        if isinstance(raw_chars, bool) or not isinstance(raw_chars, int):
            return ToolResult.failure(
                error="'max_chars' must be an integer.",
                tool_name=self.name,
            )
        max_chars = max(1, min(raw_chars, web.max_chars))
        try:
            data = self._client().fetch(url.strip(), max_chars)
        except Exception as exc:  # provider already maps to WEB_* codes
            code = getattr(exc, "code", None)
            message = getattr(exc, "message", None) or str(exc) or "fetch failed."
            if code:
                tail = message.split(": ", 1)[-1] if ": " in message else message
                return ToolResult.failure(
                    error=f"{code}: {tail}",
                    tool_name=self.name,
                )
            return ToolResult.failure(
                error=f"WEB_PROVIDER_ERROR: {message}",
                tool_name=self.name,
            )
        return ToolResult.ok(data=data, tool_name=self.name)


def build_web_tools(provider=None) -> list[Tool]:
    """Build the web tools bound to ``provider`` (default backend if None)."""
    return [WebSearchTool(provider), WebFetchTool(provider)]


def register_web_tools(registry, provider=None) -> list[str]:
    """Register web tools on ``registry``; returns the registered names."""
    names: list[str] = []
    for tool in build_web_tools(provider):
        registry.register(tool)
        names.append(tool.name)
    return names
