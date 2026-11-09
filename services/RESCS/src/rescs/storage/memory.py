"""In-memory object store (deterministic test double)."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from rescs.errors import StorageError
from rescs.interfaces.object_store import CHUNK_SIZE


class MemoryObjectStore:
    """Object store kept in process memory. Data is lost on exit; used by
    tests and demos where a real filesystem/cloud is unnecessary."""

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    def put(self, object_id: str, data: bytes) -> None:
        self._blobs[object_id] = data

    def get(self, object_id: str) -> bytes:
        try:
            return self._blobs[object_id]
        except KeyError:
            raise StorageError(
                "object not found in store", details={"object_id": object_id}
            ) from None

    def delete(self, object_id: str) -> None:
        self._blobs.pop(object_id, None)

    def exists(self, object_id: str) -> bool:
        return object_id in self._blobs

    def put_stream(self, object_id: str, chunks: Iterable[bytes]) -> None:
        self._blobs[object_id] = b"".join(c for c in chunks if c)

    def get_stream(
        self, object_id: str, chunk_size: int = CHUNK_SIZE
    ) -> Iterator[bytes]:
        try:
            data = self._blobs[object_id]
        except KeyError:
            raise StorageError(
                "object not found in store", details={"object_id": object_id}
            ) from None
        for offset in range(0, len(data), chunk_size):
            yield data[offset : offset + chunk_size]

    def size(self, object_id: str) -> int:
        try:
            return len(self._blobs[object_id])
        except KeyError:
            raise StorageError(
                "object not found in store", details={"object_id": object_id}
            ) from None
