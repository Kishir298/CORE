"""Local filesystem object store.

Stores blobs under ``<base_dir>/<object_id>``. This is the concrete default
backend; the :class:`rescs.interfaces.object_store.ObjectStore` protocol is
the seam where cloud object storage (S3-compatible, Supabase Storage) will
plug in later.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Iterable, Iterator
from pathlib import Path

from rescs.errors import StorageError
from rescs.interfaces.object_store import CHUNK_SIZE

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class LocalObjectStore:
    def __init__(self, base_dir: str | os.PathLike[str]) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def _sync_directory(self):
        if os.name != "nt":
            fd = os.open(self._base, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def _resolve(self, object_id: str) -> Path:
        if not _SAFE_ID.match(object_id):
            raise StorageError(
                "unsafe object identifier",
                details={"object_id": object_id},
            )
        # _SAFE_ID allows "." / ".." as single chars; reject them plus any
        # path separators explicitly so traversal can never resolve.
        if object_id in (".", "..") or "/" in object_id or "\\" in object_id:
            raise StorageError(
                "unsafe object identifier",
                details={"object_id": object_id},
            )
        return self._base / object_id

    def put(self, object_id: str, data: bytes) -> None:
        target = self._resolve(object_id)
        temp: Path | None = None
        try:
            temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
            with open(temp, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
            self._sync_directory()
        except OSError as exc:
            if temp is not None:
                try:
                    temp.unlink(missing_ok=True)
                except Exception:
                    pass
            raise StorageError(
                "failed to write object",
                details={"object_id": object_id, "cause": str(exc)},
            ) from exc
        except Exception:
            if temp is not None:
                try:
                    temp.unlink(missing_ok=True)
                except Exception:
                    pass
            raise

    def close(self) -> None:
        """No-op for interface parity (filesystem store holds no handle)."""
        return

    def get(self, object_id: str) -> bytes:
        target = self._resolve(object_id)
        try:
            return target.read_bytes()
        except OSError as exc:
            raise StorageError(
                "failed to read object",
                details={"object_id": object_id, "cause": str(exc)},
            ) from exc

    def delete(self, object_id: str) -> None:
        target = self._resolve(object_id)
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError(
                "failed to delete object",
                details={"object_id": object_id, "cause": str(exc)},
            ) from exc

    def exists(self, object_id: str) -> bool:
        path = self._resolve(object_id)
        return path.is_file()

    def put_stream(self, object_id: str, chunks: Iterable[bytes]) -> None:
        target = self._resolve(object_id)
        temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            with open(temp, "wb") as handle:
                for chunk in chunks:
                    if chunk:
                        handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
            self._sync_directory()
        except OSError as exc:
            temp.unlink(missing_ok=True)
            raise StorageError(
                "failed to write object stream",
                details={"object_id": object_id, "cause": str(exc)},
            ) from exc
        except Exception:
            # Non-OS failure mid-iteration (e.g. size governance aborts the
            # chunk source): never leave the temp file behind.
            temp.unlink(missing_ok=True)
            raise

    def get_stream(
        self, object_id: str, chunk_size: int = CHUNK_SIZE
    ) -> Iterator[bytes]:
        target = self._resolve(object_id)
        try:
            handle = open(target, "rb")
        except OSError as exc:
            raise StorageError(
                "failed to read object stream",
                details={"object_id": object_id, "cause": str(exc)},
            ) from exc
        try:
            while True:
                try:
                    chunk = handle.read(chunk_size)
                except OSError as exc:
                    raise StorageError(
                        "failed to read object stream",
                        details={"object_id": object_id, "cause": str(exc)},
                    ) from exc
                if not chunk:
                    break
                yield chunk
        finally:
            # Explicit close (not just `with`): abandoning the iterator
            # releases the fd deterministically on every interpreter.
            try:
                handle.close()
            except Exception:
                pass

    def size(self, object_id: str) -> int:
        target = self._resolve(object_id)
        try:
            return target.stat().st_size
        except OSError as exc:
            raise StorageError(
                "failed to stat object",
                details={"object_id": object_id, "cause": str(exc)},
            ) from exc
