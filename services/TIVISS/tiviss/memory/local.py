"""Deterministic in-memory memory backend with optional JSON file persistence."""

from __future__ import annotations

import copy
import json
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .interface import MemoryBackend, MemoryKeyError, MemoryRecord, MemorySearchResult


class LocalMemory(MemoryBackend):
    """Dictionary-backed memory store.

    When ``storage_path`` is provided the store persists to a JSON file on
    every write (``autosave=True``) or only when :meth:`save` is called
    explicitly.
    """

    def __init__(
        self, *, storage_path: str | Path | None = None, autosave: bool = True
    ) -> None:
        self._records: dict[str, MemoryRecord] = {}
        self._storage_path = Path(storage_path) if storage_path is not None else None
        self._autosave = autosave
        if self._storage_path is not None and self._storage_path.exists():
            self.load()

    def store(self, record: MemoryRecord) -> MemoryRecord:
        # Deepcopy on store/return so callers can never alias internal state.
        incoming = copy.deepcopy(record)
        existing = self._records.get(incoming.record_id)
        if existing is not None:
            incoming.created_at = existing.created_at
        self._records[incoming.record_id] = copy.deepcopy(incoming)
        self._persist()
        return copy.deepcopy(incoming)

    def retrieve(self, record_id: str) -> MemoryRecord:
        try:
            return copy.deepcopy(self._records[record_id])
        except KeyError:
            raise MemoryKeyError(record_id) from None

    def update(
        self,
        record_id: str,
        *,
        content: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> bool:
        if record_id not in self._records:
            return False
        record = self._records[record_id]
        updated = record.with_content(
            record.content if content is None else content,
            metadata=(
                record.metadata if metadata is None else copy.deepcopy(dict(metadata))
            ),
        )
        self._records[record_id] = copy.deepcopy(updated)
        self._persist()
        return True

    def delete(self, record_id: str) -> bool:
        try:
            del self._records[record_id]
        except KeyError:
            return False
        self._persist()
        return True

    def search(self, query: str, *, limit: int | None = None) -> MemorySearchResult:
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        if limit is not None:
            if isinstance(limit, bool) or not isinstance(limit, int):
                raise TypeError("limit must be an int or None")
            if limit < 0:
                raise ValueError("limit must be non-negative")
        start = time.perf_counter()
        needle = query.casefold()
        matched = [
            copy.deepcopy(record)
            for record in self._records.values()
            if needle in record.content.casefold() or needle in record.key.casefold()
        ]
        matched.sort(key=lambda r: r.updated_at, reverse=True)
        if limit is not None:
            matched = matched[:limit]
        return MemorySearchResult(
            query=query,
            total=len(matched),
            records=tuple(matched),
            elapsed_ms=(time.perf_counter() - start) * 1000,
        )

    def clear(self) -> None:
        self._records.clear()
        self._persist()

    def metadata(self) -> Mapping[str, Any]:
        return {
            "backend": "local",
            "stored": len(self._records),
            "keys": sorted(record.key for record in self._records.values()),
            "storage_path": str(self._storage_path) if self._storage_path else None,
        }

    def __contains__(self, record_id: str) -> bool:
        return record_id in self._records

    def __len__(self) -> int:
        return len(self._records)

    def _persist(self) -> None:
        if self._storage_path is not None and self._autosave:
            self.save()

    def save(self) -> None:
        """Write the store to ``storage_path`` as JSON (atomic via tmp+replace)."""
        if self._storage_path is None:
            raise RuntimeError("LocalMemory has no storage_path configured")
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"records": [record.to_dict() for record in self._records.values()]}
        payload = json.dumps(data, indent=2)
        tmp = self._storage_path.with_name(self._storage_path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self._storage_path)

    def load(self) -> None:
        """Load records from ``storage_path`` (missing file -> no-op)."""
        if self._storage_path is None or not self._storage_path.exists():
            return
        data = json.loads(self._storage_path.read_text(encoding="utf-8"))
        records = data.get("records", [])
        self._records = {
            str(record["record_id"]): MemoryRecord.from_dict(record)
            for record in records
        }
