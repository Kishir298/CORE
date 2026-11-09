"""S3-compatible and fake object stores.

``FakeS3ObjectStore`` is the test double used when no live S3 endpoint or
credentials exist. ``S3ObjectStore`` provides the same interface backed by
``boto3`` when installed; without ``boto3`` it fails fast with a clear
dependency error. Local development and tests keep using local/memory.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from rescs.errors import StorageError
from rescs.interfaces.object_store import CHUNK_SIZE
from rescs.storage.memory import MemoryObjectStore


class FakeS3ObjectStore(MemoryObjectStore):
    """In-memory S3 semantics: prefix-scoped keys, no filesystem."""

    def __init__(self, bucket: str = "fake-bucket", prefix: str = "") -> None:
        super().__init__()
        self.bucket = bucket
        self.prefix = prefix.strip("/")

    def _scoped(self, object_id: str) -> str:
        if self.prefix:
            return f"{self.prefix}/{object_id}"
        return object_id

    def put(self, object_id: str, data: bytes) -> None:
        super().put(self._scoped(object_id), data)

    def get(self, object_id: str) -> bytes:
        return super().get(self._scoped(object_id))

    def delete(self, object_id: str) -> None:
        super().delete(self._scoped(object_id))

    def exists(self, object_id: str) -> bool:
        return super().exists(self._scoped(object_id))

    def put_stream(self, object_id: str, chunks: Iterable[bytes]) -> None:
        super().put_stream(self._scoped(object_id), chunks)

    def get_stream(self, object_id: str, chunk_size: int = CHUNK_SIZE) -> Iterator[bytes]:
        yield from super().get_stream(self._scoped(object_id), chunk_size)

    def size(self, object_id: str) -> int:
        return super().size(self._scoped(object_id))


class S3ObjectStore:
    """Thin boto3-backed store. Requires ``boto3`` and valid configuration."""

    def __init__(
        self,
        *,
        endpoint: str = "",
        bucket: str,
        region: str = "",
        access_key: str = "",
        secret_key: str = "",
        prefix: str = "",
    ) -> None:
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise StorageError(
                "boto3 is required for the s3 storage backend",
                details={"hint": "pip install boto3"},
            ) from exc
        if not bucket:
            raise StorageError("RESCS_S3_BUCKET is required for s3 backend", details={})
        session_kwargs: dict = {}
        if region:
            session_kwargs["region_name"] = region
        if access_key and secret_key:
            session_kwargs.update(
                {"aws_access_key_id": access_key, "aws_secret_access_key": secret_key}
            )

        self._s3 = boto3.resource("s3", endpoint_url=endpoint or None, **session_kwargs)
        self._bucket = self._s3.Bucket(bucket)
        self._prefix = prefix.strip("/")

    def _key(self, object_id: str) -> str:
        if self._prefix:
            return f"{self._prefix}/{object_id}"
        return object_id

    def put(self, object_id: str, data: bytes) -> None:
        self.put_stream(object_id, [data])

    def get(self, object_id: str) -> bytes:
        return b"".join(self.get_stream(object_id))

    def delete(self, object_id: str) -> None:
        self._bucket.Object(self._key(object_id)).delete()

    def exists(self, object_id: str) -> bool:
        try:
            self._bucket.Object(self._key(object_id)).load()
            return True
        except Exception:
            return False

    def put_stream(self, object_id: str, chunks: Iterable[bytes]) -> None:
        import tempfile

        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as tmp:
            for c in chunks:
                if c:
                    tmp.write(c)
            tmp.seek(0)
            self._bucket.Object(self._key(object_id)).upload_fileobj(tmp)

    def get_stream(self, object_id: str, chunk_size: int = CHUNK_SIZE) -> Iterator[bytes]:
        obj = self._bucket.Object(self._key(object_id))
        try:
            body = obj.get()["Body"]
        except Exception as exc:
            raise StorageError("s3 object not found", details={"object_id": object_id}) from exc
        try:
            while True:
                try:
                    chunk = body.read(chunk_size)
                except Exception as exc:
                    raise StorageError(
                        "failed to read s3 object stream",
                        details={"object_id": object_id, "cause": str(exc)},
                    ) from exc
                if not chunk:
                    break
                yield chunk
        finally:
            try:
                body.close()
            except Exception:
                pass

    def close(self) -> None:
        """No-op for interface parity with local store."""
        return

    def size(self, object_id: str) -> int:
        try:
            return int(self._bucket.Object(self._key(object_id)).content_length)
        except Exception as exc:
            raise StorageError("s3 stat failed", details={"object_id": object_id}) from exc


def build_object_store(settings) -> object:
    """Select the configured backend without leaking credentials."""
    from rescs.storage.local import LocalObjectStore

    backend = (settings.storage_backend or "local").lower()
    if backend == "memory":
        return MemoryObjectStore()
    if backend == "s3":
        # Explicit fake only when flagged. A missing bucket with backend=s3
        # is a prod misconfiguration: fail fast instead of silently
        # returning an in-memory fake (which would look like data loss).
        endpoint = settings.s3_endpoint or ""
        if endpoint.startswith("fake:"):
            return FakeS3ObjectStore(bucket=settings.s3_bucket or "fake-bucket", prefix=settings.s3_path_prefix)
        if not settings.s3_bucket:
            from rescs.errors import ConfigurationError

            raise ConfigurationError(
                "storage_backend=s3 requires RESCS_S3_BUCKET; refusing to "
                "start with an in-memory fake."
            )
        return S3ObjectStore(
            endpoint=settings.s3_endpoint,
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            prefix=settings.s3_path_prefix,
        )
    return LocalObjectStore(settings.storage_dir)

