"""
R.E.S.C.S. (Rishik's Efficient System for Cloud Storage) interface.

R.E.S.C.S. will own persistent cloud storage for the R.I.S.A.R.M.S.
ecosystem. A.S.I.S. must not duplicate it; it exposes this interface and
switches to a real adapter only when R.E.S.C.S. is available.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StoredRecord:
    """A record persisted through the storage interface."""

    key: str
    data: dict[str, Any] = field(default_factory=dict)
    namespace: str = "default"


class StorageClient(ABC):
    """Storage surface eventually backed by R.E.S.C.S."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the adapter name."""
        raise NotImplementedError

    @abstractmethod
    def available(self) -> bool:
        """Return whether the storage backend is reachable."""
        raise NotImplementedError

    @abstractmethod
    def store(self, record: StoredRecord) -> bool:
        """Persist a record."""
        raise NotImplementedError

    @abstractmethod
    def retrieve(self, key: str, namespace: str = "default") -> StoredRecord | None:
        """Retrieve a record by key."""
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str, namespace: str = "default") -> list[StoredRecord]:
        """Search records by content."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, key: str, namespace: str = "default") -> bool:
        """Delete a record."""
        raise NotImplementedError
