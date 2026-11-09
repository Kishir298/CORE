"""
R.E.S.C.S. adapter placeholder.

This adapter is NOT wired into A.S.I.S. It documents the integration
point and raises a clear error until the R.E.S.C.S. project provides a
real client through C.O.R.E.
"""

from __future__ import annotations

from asis.errors import MemoryError
from asis.logging.logger import get_logger

from .client import StorageClient, StoredRecord

_UNAVAILABLE_MESSAGE = (
    "R.E.S.C.S. is not available. A.S.I.S. uses its local memory "
    "provider until the R.E.S.C.S. integration is established."
)


class RESCSAdapter(StorageClient):
    """Placeholder adapter that reports R.E.S.C.S. as unavailable."""

    def __init__(self) -> None:
        self._logger = get_logger("integrations.rescs")

    @property
    def name(self) -> str:
        return "rescs"

    def available(self) -> bool:
        return False

    def store(self, record: StoredRecord) -> bool:
        raise MemoryError(_UNAVAILABLE_MESSAGE)

    def retrieve(self, key: str, namespace: str = "default") -> StoredRecord | None:
        raise MemoryError(_UNAVAILABLE_MESSAGE)

    def search(self, query: str, namespace: str = "default") -> list[StoredRecord]:
        raise MemoryError(_UNAVAILABLE_MESSAGE)

    def delete(self, key: str, namespace: str = "default") -> bool:
        raise MemoryError(_UNAVAILABLE_MESSAGE)
