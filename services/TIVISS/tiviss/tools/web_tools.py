"""Basic web access tools for T.I.V.I.S.S.: web_search and web_fetch."""

from __future__ import annotations

from typing import Any

from ..configuration import settings as tiviss_settings
from ..permissions.permissions import Permission
from .interface import Tool, ToolError, ToolResult, ToolStatus


def _web_settings():
    return tiviss_settings.web


def _disabled_result(tool_name: str) -> ToolResult:
    return ToolResult(
        tool_id=tool_name,
        status=ToolStatus.FAILED,
        error="WEB_DISABLED: web access is disabled by configuration.",
    )


class WebSearchTool(Tool):
    """Search the web and return bounded structured results."""

    @property
    def tool_id(self) -> str:
        return "web_search"

    @property
    def name(self) -> str:
        return "WebSearch"

    @property
    def description(self) -> str:
        return "Search the web for information. Returns short structured results (title, url, snippet, source)."

    @property
    def permission(self) -> Permission:
        return Permission.of("tools.web")

    def __init__(self, provider=None) -> None:
        self._provider = provider

    def _client(self):
        if self._provider is not None:
            return self._provider
        from tiviss.web.provider import build_default_provider

        return build_default_provider()

    def validate_input(self, params: dict[str, Any]) -> dict[str, Any]:
        web = _web_settings()
        if not web.enabled:
            raise ToolError("WEB_DISABLED: web access is disabled by configuration.")
        query = params.get("query", "")
        if not isinstance(query, str) or not query.strip():
            raise ToolError("query must be a non-empty string.")
        if len(query.strip()) > web.max_query_length:
            raise ToolError("query exceeds the maximum permitted length.")
        raw_count = params.get("max_results", web.max_results)
        if isinstance(raw_count, bool) or not isinstance(raw_count, int):
            raise ToolError("max_results must be an integer.")
        count = max(1, min(raw_count, web.max_results))
        return {"query": query.strip(), "count": count}

    def execute(self, params: dict[str, Any]) -> ToolResult:
        validated = self.validate_input(params)
        try:
            results = self._client().search(validated["query"], validated["count"])
        except Exception as exc:
            code = getattr(exc, "code", None)
            message = getattr(exc, "message", None) or str(exc) or "search failed."
            if code:
                return ToolResult(
                    tool_id=self.tool_id,
                    status=ToolStatus.FAILED,
                    error=f"{code}: {message.split(': ', 1)[-1]}" if ": " in message else f"{code}: {message}",
                )
            return ToolResult(
                tool_id=self.tool_id,
                status=ToolStatus.FAILED,
                error=f"WEB_PROVIDER_ERROR: {message}",
            )
        bounded = list(results or [])[:validated["count"]]
        return ToolResult(
            tool_id=self.tool_id,
            status=ToolStatus.OK,
            output={"query": validated["query"], "results": bounded},
        )


class WebFetchTool(Tool):
    """Fetch readable content from a public HTTP/HTTPS page."""

    @property
    def tool_id(self) -> str:
        return "web_fetch"

    @property
    def name(self) -> str:
        return "WebFetch"

    @property
    def description(self) -> str:
        return "Fetch readable content from a public HTTP(S) webpage. Returns bounded text plus page metadata."

    @property
    def permission(self) -> Permission:
        return Permission.of("tools.web")

    def __init__(self, provider=None) -> None:
        self._provider = provider

    def _client(self):
        if self._provider is not None:
            return self._provider
        from tiviss.web.provider import build_default_provider

        return build_default_provider()

    def validate_input(self, params: dict[str, Any]) -> dict[str, Any]:
        web = _web_settings()
        if not web.enabled:
            raise ToolError("WEB_DISABLED: web access is disabled by configuration.")
        url = params.get("url", "")
        if not isinstance(url, str) or not url.strip():
            raise ToolError("url must be a non-empty string.")
        if len(url.strip()) > web.max_url_length:
            raise ToolError("url exceeds the maximum permitted length.")
        from urllib.parse import urlparse as _urlparse

        _parsed = _urlparse(url.strip())
        _scheme = (_parsed.scheme or "").lower()
        if _scheme not in ("http", "https"):
            if not _scheme or not _parsed.hostname:
                raise ToolError("WEB_INVALID_URL: url must be a valid http(s) URL.")
            raise ToolError("WEB_UNSUPPORTED_SCHEME: only http and https URLs are permitted.")
        raw_chars = params.get("max_chars", web.max_chars)
        if isinstance(raw_chars, bool) or not isinstance(raw_chars, int):
            raise ToolError("max_chars must be an integer.")
        max_chars = max(1, min(raw_chars, web.max_chars))
        return {"url": url.strip(), "max_chars": max_chars}

    def execute(self, params: dict[str, Any]) -> ToolResult:
        validated = self.validate_input(params)
        try:
            data = self._client().fetch(validated["url"], validated["max_chars"])
        except Exception as exc:
            code = getattr(exc, "code", None)
            message = getattr(exc, "message", None) or str(exc) or "fetch failed."
            if code:
                return ToolResult(
                    tool_id=self.tool_id,
                    status=ToolStatus.FAILED,
                    error=f"{code}: {message.split(': ', 1)[-1]}" if ": " in message else f"{code}: {message}",
                )
            return ToolResult(
                tool_id=self.tool_id,
                status=ToolStatus.FAILED,
                error=f"WEB_PROVIDER_ERROR: {message}",
            )
        return ToolResult(
            tool_id=self.tool_id,
            status=ToolStatus.OK,
            output={
                "url": data.url,
                "title": data.title,
                "content": data.content,
                "metadata": data.metadata,
            },
        )


def build_web_tools(provider=None) -> list[Tool]:
    """Build the web tools bound to provider (default backend if None)."""
    return [WebSearchTool(provider), WebFetchTool(provider)]


def register_web_tools(registry, provider=None) -> list[str]:
    """Register web tools on registry; returns the registered names."""
    names: list[str] = []
    for tool in build_web_tools(provider):
        registry.register(tool)
        names.append(tool.tool_id)
    return names