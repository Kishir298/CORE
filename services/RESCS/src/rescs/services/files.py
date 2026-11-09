"""File storage service.

Stores binary content (blob) in an object store and its descriptive
metadata (filename, MIME type, size, SHA-256, etag, timestamps) in the
record-keeping repository. Metadata and bytes are deliberately separate, so
large payloads never live inside database rows.

v0.2 additions: soft delete / restore / purge (blobs survive soft delete so
restore is instant), TTL expiry, tags, quotas, expiry cleanup.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable, Iterator
from datetime import datetime

from rescs.config import Settings
from rescs.domain import (
    FileObjectData,
    Page,
    ensure_utc,
    normalize_tags,
    utcnow,
    validate_tags,
)
from rescs.errors import (
    ConflictError,
    InvalidRequestError,
    NotFoundError,
    PayloadTooLargeError,
    PreconditionFailedError,
    QuotaExceededError,
    RESCSError,
    StorageError,
)
from rescs.etag import file_etag
from rescs.interfaces.object_store import ObjectStore
from rescs.interfaces.repository import FileObjectRepository
from rescs.logging import get_logger
from rescs.schemas.file_object import FileObjectCreate
from rescs.services.audit import AuditService
from rescs.services.expiry import resolve_expiry
from rescs.services.utils import clamp_pagination

logger = get_logger(__name__)

DEFAULT_LIMIT = 100


class FileService:
    def __init__(
        self,
        repository: FileObjectRepository,
        object_store: ObjectStore,
        *,
        settings: Settings | None = None,
        audit: AuditService | None = None,
    ) -> None:
        self._repo = repository
        self._store = object_store
        self._settings = settings
        self._audit = audit

    @property
    def object_store(self) -> ObjectStore:
        return self._store

    # -- internal helpers -------------------------------------------------

    def _audited(self, operation: str, meta: FileObjectData | None, error: Exception | None = None, owner: str = "system") -> None:
        if self._audit is None:
            return
        resource_id = meta.id if meta else None
        resource_owner = meta.owner if meta else owner
        if error is None:
            self._audit.log(
                operation,
                resource_type="file",
                resource_id=resource_id,
                owner=resource_owner,
            )
        else:
            code = error.code if isinstance(error, RESCSError) else type(error).__name__
            self._audit.log(
                operation,
                resource_type="file",
                resource_id=resource_id,
                owner=resource_owner,
                outcome="denied" if code in ("UNAUTHORIZED", "FORBIDDEN") else "error",
                error_code=code,
            )

    def _check_governance(self, owner: str, size: int, metadata: dict) -> None:
        if self._settings is None:
            return
        settings = self._settings
        if settings.max_file_size and size > settings.max_file_size:
            raise PayloadTooLargeError(
                f"file exceeds maximum size of {settings.max_file_size} bytes",
                details={"size": size, "max": settings.max_file_size},
            )
        meta_size = len(json.dumps(metadata, default=str))
        if settings.max_metadata_bytes and meta_size > settings.max_metadata_bytes:
            raise PayloadTooLargeError(
                f"metadata exceeds {settings.max_metadata_bytes} bytes",
                details={"size": meta_size, "max": settings.max_metadata_bytes},
            )
        if settings.max_files_per_owner:
            count = self._repo.count_by_owner(owner)
            if count >= settings.max_files_per_owner:
                raise QuotaExceededError(
                    f"owner {owner!r} reached the file limit",
                    details={"owner": owner, "count": count, "max": settings.max_files_per_owner},
                )
        if settings.max_bytes_per_owner:
            used = self._repo.bytes_by_owner(owner)
            if used + size > settings.max_bytes_per_owner:
                raise QuotaExceededError(
                    f"owner {owner!r} would exceed the storage byte limit",
                    details={"owner": owner, "used": used, "size": size, "max": settings.max_bytes_per_owner},
                )

    @staticmethod
    def _validate_expiry(expires_at: datetime | None) -> datetime | None:
        if expires_at is None:
            return None
        moment = ensure_utc(expires_at)
        if moment <= utcnow():
            raise InvalidRequestError(
                "expires_at must be in the future",
                details={"expires_at": moment.isoformat()},
            )
        return moment

    def _resolve_expiry(
        self, expires_at: datetime | None, ttl_seconds: int | None
    ) -> datetime | None:
        return resolve_expiry(expires_at, ttl_seconds, self._settings)

    def _enforce_post_write_quota(self, owner: str, file_id: str) -> None:
        """Race-safe post-write quota check; rolls back on over-quota."""
        if self._settings is None:
            return
        over = False
        details: dict = {"owner": owner}
        if self._settings.max_files_per_owner:
            count = self._repo.count_by_owner(owner)
            if count > self._settings.max_files_per_owner:
                over = True
                details.update({"count": count, "max": self._settings.max_files_per_owner})
        if not over and self._settings.max_bytes_per_owner:
            used = self._repo.bytes_by_owner(owner)
            if used > self._settings.max_bytes_per_owner:
                over = True
                details.update({"used": used, "max": self._settings.max_bytes_per_owner})
        if over:
            try:
                self._repo.delete(file_id)
            except Exception:
                pass
            try:
                self._store.delete(file_id)
            except Exception:
                pass
            raise QuotaExceededError(f"owner {owner!r} exceeded storage quota", details=details)

    # -- lifecycle ----------------------------------------------------------

    def create(
        self,
        payload: FileObjectCreate,
        data: bytes,
        *,
        actor: str = "system",
    ) -> FileObjectData:
        try:
            tags = normalize_tags(payload.tags)
            validate_tags(tags)
            expires_at = self._resolve_expiry(
                payload.expires_at, getattr(payload, "ttl_seconds", None)
            )
            if payload.idempotency_key is not None:
                existing = self._repo.find_by_idempotency_key(payload.idempotency_key)
                if existing is not None:
                    if existing.owner != payload.owner:
                        from rescs.errors import ForbiddenError
                        raise ForbiddenError("idempotency owner mismatch", details={})
                    if existing.deleted_at is not None:
                        raise ConflictError(
                            "idempotency key belongs to a deleted file;"
                            " purge it or use a new key",
                            details={"idempotency_key": payload.idempotency_key},
                        ) from None
                    if existing.is_expired():
                        self._purge_row(existing)
                    else:
                        return existing
            self._check_governance(payload.owner, len(data), payload.metadata)

            digest = hashlib.sha256(data).hexdigest()
            size = len(data)
            now = utcnow()
            file_id = str(uuid.uuid4())

            self._store.put(file_id, data)

            file_object = FileObjectData(
                id=file_id,
                filename=payload.filename,
                mime_type=payload.mime_type,
                size=size,
                storage_path=file_id,
                sha256=digest,
                metadata=payload.metadata,
                owner=payload.owner,
                version=1,
                idempotency_key=payload.idempotency_key,
                etag=file_etag(digest, size),
                created_at=now,
                updated_at=now,
                tags=tags,
                expires_at=expires_at,
            )
            try:
                created = self._repo.create(file_object)
            except Exception:
                self._store.delete(file_id)
                raise
            self._enforce_post_write_quota(payload.owner, created.id)
            self._audited("file.upload", created)
            return created
        except Exception as exc:
            self._audited("file.upload", None, exc, owner=payload.owner)
            raise

    def create_stream(
        self,
        payload: FileObjectCreate,
        chunks: Iterable[bytes],
        *,
        actor: str = "system",
    ) -> FileObjectData:
        """Store a file from a chunk iterable with bounded memory.

        Streams chunks to the object store while computing SHA-256/size,
        then validates governance before publishing metadata. Failures
        never leave orphan blobs or partial metadata visible.
        """
        file_id = str(uuid.uuid4())
        digest = hashlib.sha256()
        size = 0
        max_size = self._settings.max_file_size if self._settings else 0
        try:
            tags = normalize_tags(payload.tags)
            validate_tags(tags)
            expires_at = self._resolve_expiry(
                payload.expires_at, getattr(payload, "ttl_seconds", None)
            )
            if payload.idempotency_key is not None:
                existing = self._repo.find_by_idempotency_key(payload.idempotency_key)
                if existing is not None:
                    if existing.owner != payload.owner:
                        from rescs.errors import ForbiddenError
                        raise ForbiddenError("idempotency owner mismatch", details={})
                    if existing.deleted_at is not None:
                        raise ConflictError(
                            "idempotency key belongs to a deleted file;"
                            " purge it or use a new key",
                            details={"idempotency_key": payload.idempotency_key},
                        ) from None
                    if existing.is_expired():
                        self._purge_row(existing)
                    else:
                        # Drain caller's iterator to keep connection state sane.
                        for _ in chunks:
                            pass
                        return existing

            def _bounded() -> Iterator[bytes]:
                nonlocal size
                for chunk in chunks:
                    if not chunk:
                        continue
                    size += len(chunk)
                    if max_size and size > max_size:
                        raise PayloadTooLargeError(
                            f"file exceeds maximum size of {max_size} bytes",
                            details={"size": size, "max": max_size},
                        )
                    digest.update(chunk)
                    yield chunk

            self._store.put_stream(file_id, _bounded())
            # Governance (quotas/metadata) after size is known; cleanup on deny.
            self._check_governance(payload.owner, size, payload.metadata)
            now = utcnow()
            hex_digest = digest.hexdigest()
            file_object = FileObjectData(
                id=file_id,
                filename=payload.filename,
                mime_type=payload.mime_type,
                size=size,
                storage_path=file_id,
                sha256=hex_digest,
                metadata=payload.metadata,
                owner=payload.owner,
                version=1,
                idempotency_key=payload.idempotency_key,
                etag=file_etag(hex_digest, size),
                created_at=now,
                updated_at=now,
                tags=tags,
                expires_at=expires_at,
            )
            try:
                created = self._repo.create(file_object)
            except Exception:
                self._store.delete(file_id)
                raise
            self._enforce_post_write_quota(payload.owner, created.id)
            self._audited("file.upload", created)
            return created
        except Exception as exc:
            try:
                self._store.delete(file_id)
            except Exception:
                pass
            self._audited("file.upload", None, exc, owner=payload.owner)
            raise

    def get(self, file_id: str, *, actor: str = "system") -> FileObjectData:
        return self._repo.get(file_id)

    def get_including_deleted(self, file_id: str) -> FileObjectData:
        return self._repo.get_including_deleted(file_id)

    def download(
        self, file_id: str, *, actor: str = "system", verify: bool = True
    ) -> tuple[FileObjectData, bytes]:
        target: FileObjectData | None = None
        try:
            target = self._repo.get(file_id)
            file_object = target
            data = self._store.get(file_object.storage_path)
            if verify:
                actual = hashlib.sha256(data).hexdigest()
                if actual != file_object.sha256:
                    raise StorageError(
                        "blob integrity check failed; stored bytes do not match metadata",
                        details={
                            "id": file_id,
                            "expected_sha256": file_object.sha256,
                            "actual_sha256": actual,
                        },
                    )
            self._audited("file.download", file_object)
            return file_object, data
        except Exception as exc:
            self._audited("file.download", target, exc)
            raise

    def download_stream(
        self, file_id: str, *, actor: str = "system", chunk_size: int = 1024 * 1024
    ) -> tuple[FileObjectData, Iterator[bytes]]:
        """Return metadata plus a bounded-memory byte iterator.

        The iterator verifies incremental SHA-256 as it yields: a corrupt
        blob aborts the stream with StorageError instead of returning 200
        with bad bytes. Callers serving HTTP should also expose the
        expected digest (X-File-SHA256) so clients can verify independently.
        """
        file_object = self._repo.get(file_id)
        expected = file_object.sha256
        inner = self._store.get_stream(file_object.storage_path, chunk_size)

        def _verifying() -> Iterator[bytes]:
            digest = hashlib.sha256()
            exhausted = False
            try:
                for chunk in inner:
                    digest.update(chunk)
                    yield chunk
                exhausted = True
            finally:
                try:
                    close = getattr(inner, "close", None)
                    if callable(close):
                        close()
                except Exception:
                    pass
            # Abandoned (partially-consumed) streams must not raise
            # integrity errors on GeneratorExit/close; only a fully
            # consumed stream with a digest mismatch fails.
            if exhausted and digest.hexdigest() != expected:
                raise StorageError(
                    "blob integrity check failed during stream; stored bytes "
                    "do not match metadata",
                    details={"id": file_id, "expected_sha256": expected},
                )

        self._audited("file.download", file_object)
        return file_object, _verifying()

    def delete(
        self,
        file_id: str,
        *,
        actor: str = "system",
        expected_etag: str | None = None,
    ) -> None:
        """Soft-delete: metadata tombstoned, blob retained for instant restore."""
        target: FileObjectData | None = None
        try:
            target = self._repo.get(file_id)
            file_object = target
            if expected_etag is not None and file_object.etag != expected_etag:
                raise PreconditionFailedError(
                    "etag does not match current file state",
                    details={
                        "id": file_id,
                        "expected_etag": expected_etag,
                        "current_etag": file_object.etag,
                        "version": file_object.version,
                    },
                )
            tombstone = FileObjectData(
                id=file_object.id,
                filename=file_object.filename,
                mime_type=file_object.mime_type,
                size=file_object.size,
                storage_path=file_object.storage_path,
                sha256=file_object.sha256,
                metadata=file_object.metadata,
                owner=file_object.owner,
                version=file_object.version + 1,
                idempotency_key=file_object.idempotency_key,
                etag=file_object.etag,
                created_at=file_object.created_at,
                updated_at=utcnow(),
                tags=file_object.tags,
                expires_at=file_object.expires_at,
                deleted_at=utcnow(),
                deleted_by=actor,
            )
            self._repo.update(tombstone)
            self._audited("file.delete", tombstone)
        except Exception as exc:
            self._audited("file.delete", target, exc)
            raise

    def restore(
        self,
        file_id: str,
        *,
        actor: str = "system",
        expected_etag: str | None = None,
    ) -> FileObjectData:
        target: FileObjectData | None = None
        try:
            target = self._repo.get_including_deleted(file_id)
            existing = target
            if existing.deleted_at is None:
                raise InvalidRequestError(
                    "file is not deleted", details={"id": file_id}
                )
            if expected_etag is not None and existing.etag != expected_etag:
                raise PreconditionFailedError(
                    "etag does not match current file state",
                    details={
                        "id": file_id,
                        "expected_etag": expected_etag,
                        "current_etag": existing.etag,
                        "version": existing.version,
                    },
                )
            # The blob must still be there or restore would resurrect metadata
            # pointing at nothing.
            if not self._store.exists(existing.storage_path):
                raise StorageError(
                    "cannot restore file; stored bytes are missing",
                    details={"id": file_id},
                )
            restored = FileObjectData(
                id=existing.id,
                filename=existing.filename,
                mime_type=existing.mime_type,
                size=existing.size,
                storage_path=existing.storage_path,
                sha256=existing.sha256,
                metadata=existing.metadata,
                owner=existing.owner,
                version=existing.version + 1,
                idempotency_key=existing.idempotency_key,
                etag=existing.etag,
                created_at=existing.created_at,
                updated_at=utcnow(),
                tags=existing.tags,
                expires_at=existing.expires_at,
                deleted_at=None,
                deleted_by=None,
            )
            result = self._repo.update(restored)
            self._audited("file.restore", result)
            return result
        except Exception as exc:
            self._audited("file.restore", target, exc)
            raise

    def purge(
        self,
        file_id: str,
        *,
        actor: str = "system",
        expected_etag: str | None = None,
    ) -> None:
        """Permanently remove file metadata and (best-effort) its blob."""
        target: FileObjectData | None = None
        try:
            target = self._repo.get_including_deleted(file_id)
            existing = target
            if expected_etag is not None and existing.etag != expected_etag:
                raise PreconditionFailedError(
                    "etag does not match current file state",
                    details={
                        "id": file_id,
                        "expected_etag": expected_etag,
                        "current_etag": existing.etag,
                        "version": existing.version,
                    },
                )
            self._purge_row(existing)
            self._audited("file.purge", existing)
        except Exception as exc:
            self._audited("file.purge", target, exc)
            raise

    def _purge_row(self, file_object: FileObjectData) -> None:
        self._repo.delete(file_object.id)
        try:
            self._store.delete(file_object.storage_path)
        except Exception:
            logger.warning(
                "blob cleanup failed for file %s (metadata already removed)",
                file_object.id,
            )

    def list(
        self,
        actor: str = "system",
        *,
        owner: str | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        tags: list[str] | None = None,
        mime_type: str | None = None,
        size_min: int | None = None,
        size_max: int | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        updated_after: datetime | None = None,
        updated_before: datetime | None = None,
        include_deleted: bool = False,
        include_expired: bool = False,
    ) -> Page[FileObjectData]:
        limit, offset = clamp_pagination(limit, offset)
        return self._repo.list(
            owner=owner,
            limit=limit,
            offset=offset,
            tags=tags,
            mime_type=mime_type,
            size_min=size_min,
            size_max=size_max,
            created_after=created_after,
            created_before=created_before,
            updated_after=updated_after,
            updated_before=updated_before,
            include_deleted=include_deleted,
            include_expired=include_expired,
        )

    def list_deleted(
        self,
        actor: str = "system",
        *,
        owner: str | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> Page[FileObjectData]:
        limit, offset = clamp_pagination(limit, offset)
        return self._repo.list_deleted(owner=owner, limit=limit, offset=offset)

    def count_expired(self, *, limit: int = 500) -> int:
        """Number of expired files awaiting cleanup (bounded preview)."""
        return len(self._repo.list_expired(utcnow(), limit=limit))

    def cleanup_expired(self, *, actor: str = "system", limit: int = 500) -> int:
        """Purge expired files (metadata + blob); returns the number purged."""
        expired = self._repo.list_expired(utcnow(), limit=limit)
        purged = 0
        for item in expired:
            try:
                self._purge_row(item)
                purged += 1
            except NotFoundError:
                continue
        if self._audit is not None:
            self._audit.log("file.cleanup", resource_type="file", owner=actor)
        return purged

