"""Memory interface and record model.

The memory interface is intentionally independent of R.E.S.C.S.:
T.I.V.I.S.S. defines the contract, a local backend implements it for
development, and a future R.E.S.C.S. adapter can implement the same contract
for persistent cloud storage.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def utcnow() -> datetime:
    return datetime.now(UTC)


class MemoryKeyError(KeyError):
    """Raised when a memory record does not exist."""

    def __init__(self, record_id: str) -> None:
        self.record_id = record_id
        super().__init__(f"memory record not found: {record_id}")


@dataclass
class MemoryRecord:
    """A stored unit of memory."""

    key: str
    content: str
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def with_content(
        self, content: str, *, metadata: Mapping[str, Any] | None = None
    ) -> MemoryRecord:
        modified = MemoryRecord(
            key=self.key,
            content=content,
            record_id=self.record_id,
            metadata=self.metadata if metadata is None else dict(metadata),
            created_at=self.created_at,
            updated_at=utcnow(),
        )
        return modified

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "key": self.key,
            "content": self.content,
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MemoryRecord:
        def _parse(value: str) -> datetime:
            return datetime.fromisoformat(value)

        return cls(
            record_id=str(data["record_id"]),
            key=str(data["key"]),
            content=str(data["content"]),
            metadata=dict(data.get("metadata") or {}),
            created_at=_parse(data["created_at"]),
            updated_at=_parse(data["updated_at"]),
        )


@dataclass(frozen=True)
class MemorySearchResult:
    """Result set for a memory search."""

    query: str
    total: int
    records: tuple[MemoryRecord, ...]
    elapsed_ms: float = 0.0


class MemoryBackend(ABC):
    """Contract for a memory store (local, cloud, disk, etc.)."""

    @abstractmethod
    def store(self, record: MemoryRecord) -> MemoryRecord:
        """Store a record (create or update by record_id)."""

    @abstractmethod
    def retrieve(self, record_id: str) -> MemoryRecord:
        """Return a record by ID or raise :class:`MemoryKeyError`."""

    @abstractmethod
    def update(
        self,
        record_id: str,
        *,
        content: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> bool:
        """Update content/metadata of a record. Returns False when missing."""

    @abstractmethod
    def delete(self, record_id: str) -> bool:
        """Delete a record. Returns False when missing."""

    @abstractmethod
    def search(self, query: str, *, limit: int | None = None) -> MemorySearchResult:
        """Search records whose key or content contains ``query`` (case-insensitive)."""

    @abstractmethod
    def clear(self) -> None:
        """Remove all records."""

    @abstractmethod
    def metadata(self) -> Mapping[str, Any]:
        """Return backend statistics (record counts, keys, etc.)."""
