"""
Memory search interface for A.S.I.S.

DEPRECATED: thin wrapper kept for backwards compatibility. New code must
use :meth:`MemoryManager.search_context` (query-scoped, bounded) instead
of raw storage search; dumping raw matches into prompts bypasses
relevance ranking, limits, and the data-vs-instructions separation.
"""

from __future__ import annotations

import warnings

from .models import Memory, MemoryCategory
from .storage import MemoryStorage


class MemorySearch:
    """Search interface for persistent memory (deprecated wrapper)."""

    def __init__(self, storage: MemoryStorage) -> None:
        warnings.warn(
            "MemorySearch is deprecated; use MemoryManager.search_context instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.storage = storage

    def text(
        self,
        query: str,
        category: MemoryCategory | None = None,
    ) -> list[Memory]:
        """Search memory using text matching."""
        return self.storage.search(query, category=category)
