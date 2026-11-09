"""
Bounded local translation cache.

Pure in-memory LRU keyed by (text, source, target). Local only, no
network, no persistence — nothing is stored forever and nothing leaves
the process.
"""

from __future__ import annotations

from collections import OrderedDict


class TranslationCache:
    """Fixed-size LRU cache for translation results."""

    def __init__(self, max_size: int = 200, enabled: bool = True) -> None:
        self._max_size = max(1, int(max_size))
        self._enabled = bool(enabled)
        self._entries: OrderedDict[tuple[str, str, str], str] = OrderedDict()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def max_size(self) -> int:
        return self._max_size

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, text: str, source: str, target: str) -> str | None:
        if not self._enabled:
            return None
        key = (text, source, target)
        if key not in self._entries:
            return None
        self._entries.move_to_end(key)
        return self._entries[key]

    def put(self, text: str, source: str, target: str, translated: str) -> None:
        if not self._enabled:
            return
        key = (text, source, target)
        self._entries[key] = translated
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_size:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()
