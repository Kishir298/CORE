"""Shared fixtures for A.S.I.S. tests."""

from __future__ import annotations

import os
import pytest

from asis.memory import MemoryDatabase, MemoryManager, MemoryStorage


# External validation markers for live tests
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "needs_real: requires live voice/translation/web (ASIS_REAL_VOICE_TESTS=1, ASIS_TRANSLATION_LIVE=1, ASIS_WEB_LIVE=1)"
    )

def pytest_collection_modifyitems(config, items):
    live_voice = os.environ.get("ASIS_REAL_VOICE_TESTS") == "1"
    live_translation = os.environ.get("ASIS_TRANSLATION_LIVE") == "1"
    live_web = os.environ.get("ASIS_WEB_LIVE") == "1"
    if not (live_voice or live_translation or live_web):
        skip_real = pytest.mark.skip(reason="Live test env vars not set (ASIS_REAL_VOICE_TESTS=1, ASIS_TRANSLATION_LIVE=1, ASIS_WEB_LIVE=1)")
        for item in items:
            if "needs_real" in item.keywords:
                item.add_marker(skip_real)


@pytest.fixture()
def memory_manager(tmp_path) -> MemoryManager:
    """A memory manager backed by a temporary SQL file database."""
    database = MemoryDatabase(tmp_path / "memory.db")
    return MemoryManager(MemoryStorage(database))
