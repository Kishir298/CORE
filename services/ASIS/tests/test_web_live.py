"""Opt-in live network validation for basic web access.

Skipped by default. Run explicitly with real internet access:

    ASIS_WEB_LIVE=1 python3 -m pytest tests/test_web_live.py -v

Uses only safe public endpoints, strict timeouts, and no credentials.
Never faked: failures here reflect the real network/provider.
"""

from __future__ import annotations

import os

import pytest

from asis.web.provider import DuckDuckGoWebProvider

pytestmark = pytest.mark.skipif(
    os.getenv("ASIS_WEB_LIVE") != "1",
    reason="live network tests require ASIS_WEB_LIVE=1",
)


def test_live_fetch_example_com():
    provider = DuckDuckGoWebProvider(timeout=10)
    out = provider.fetch("https://example.com/", 8000)
    assert out["status_code"] == 200
    assert out["text"]
    assert out["truncated"] is False


def test_live_search_returns_structured_results():
    provider = DuckDuckGoWebProvider(timeout=10)
    results = provider.search("A.S.I.S.", max_results=3)
    assert isinstance(results, list)
    for entry in results:
        assert {"title", "url", "snippet", "source"} <= set(entry)
        assert entry["url"].startswith(("http://", "https://"))
