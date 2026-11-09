"""Web provider abstraction for T.I.V.I.S.S."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, List
from ..configuration import settings as tiviss_settings
from ..errors import TivissError


def _web_settings():
    return tiviss_settings.web


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str


@dataclass
class FetchResult:
    url: str
    title: str
    content: str
    metadata: dict[str, Any]


class WebProviderError(TivissError):
    pass


class WebProvider(ABC):
    """Abstract web provider interface."""

    @abstractmethod
    def search(self, query: str, count: int) -> List[SearchResult]:
        pass

    @abstractmethod
    def fetch(self, url: str, max_chars: int) -> FetchResult:
        pass


class MockWebProvider(WebProvider):
    """Mock provider for testing and offline use."""

    def search(self, query: str, count: int) -> List[SearchResult]:
        return [SearchResult(
            title="Mock result for: " + query,
            url="https://example.com",
            snippet="This is a mock search result.",
            source="mock"
        )]

    def fetch(self, url: str, max_chars: int) -> FetchResult:
        return FetchResult(
            url=url,
            title="Mock Page",
            content="Mock content for " + url[:50],
            metadata={"mock": True}
        )


def build_default_provider() -> WebProvider:
    web = _web_settings()
    if not web.enabled:
        return MockWebProvider()
    # For now, return mock provider. Real implementation would go here.
    return MockWebProvider()
