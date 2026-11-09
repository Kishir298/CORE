"""Storage abstraction: object store interface (binary blobs)."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Protocol, runtime_checkable

CHUNK_SIZE = 1024 * 1024  # 1 MiB streaming chunks


@runtime_checkable
class ObjectStore(Protocol):
    """Binary object storage. Backends: local filesystem / memory (default) + S3-compatible (implemented, + fake for tests).

    Small payloads may use :meth:`put`/:meth:`get`. Large payloads MUST use
    :meth:`put_stream`/:meth:`get_stream` to keep memory bounded.
    """

    def put(self, object_id: str, data: bytes) -> None: ...

    def get(self, object_id: str) -> bytes: ...

    def delete(self, object_id: str) -> None: ...

    def exists(self, object_id: str) -> bool: ...

    def put_stream(self, object_id: str, chunks: Iterable[bytes]) -> None:
        """Store bytes from an iterable of chunks without buffering all."""
        ...

    def get_stream(
        self, object_id: str, chunk_size: int = CHUNK_SIZE
    ) -> Iterator[bytes]:
        """Yield stored bytes in bounded chunks."""
        ...

    def size(self, object_id: str) -> int:
        """Return stored byte length without loading the object."""
        ...
