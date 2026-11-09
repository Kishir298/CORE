"""Resumable upload service: chunked sessions with integrity + expiry."""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from collections.abc import Iterator
from datetime import timedelta

from rescs.config import Settings
from rescs.domain import (
    FileObjectData,
    UploadSessionData,
    normalize_tags,
    utcnow,
    validate_tags,
)
from rescs.errors import (
    ConflictError,
    InvalidRequestError,
    NotFoundError,
    PayloadTooLargeError,
    QuotaExceededError,
    RESCSError,
)
from rescs.etag import file_etag
from rescs.interfaces.object_store import ObjectStore
from rescs.interfaces.repository import FileObjectRepository, UploadSessionRepository
from rescs.services.audit import AuditService

MIN_CHUNK = 64 * 1024  # 64 KiB
MAX_CHUNK = 64 * 1024 * 1024  # 64 MiB
DEFAULT_CHUNK = 8 * 1024 * 1024  # 8 MiB
MAX_SESSION_SECONDS = 24 * 3600  # 24h


def _chunk_key(session_id: str, offset: int) -> str:
    return f"{session_id}__chunk__{offset:020d}"


class UploadService:
    def __init__(
        self,
        sessions: UploadSessionRepository,
        files_repo: FileObjectRepository,
        object_store: ObjectStore,
        *,
        settings: Settings | None = None,
        audit: AuditService | None = None,
    ) -> None:
        self._sessions = sessions
        self._files = files_repo
        self._store = object_store
        self._settings = settings
        self._audit = audit
        self._locks_guard = threading.Lock()
        self._finalize_locks: dict[str, threading.Lock] = {}

    def _finalize_lock(self, session_id: str) -> threading.Lock:
        with self._locks_guard:
            lock = self._finalize_locks.get(session_id)
            if lock is None:
                lock = threading.Lock()
                self._finalize_locks[session_id] = lock
            return lock

    def _check_owner_locked(self, resource_owner: str) -> None:
        from rescs.errors import ForbiddenError

        from rescs.gateway_scope import current_owner
        locked = current_owner.get() or (self._settings.api_key_owner if self._settings else "")
        if locked and resource_owner != locked:
            raise ForbiddenError(
                f"this resource belongs to owner {resource_owner!r}",
                details={"owner": resource_owner},
            )

    def _check_finalize_governance(self, owner: str, size: int, metadata: dict) -> None:
        settings = self._settings
        if settings is None:
            return
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
            count = self._files.count_by_owner(owner)
            if count >= settings.max_files_per_owner:
                raise QuotaExceededError(
                    f"owner {owner!r} reached the file limit",
                    details={"owner": owner, "count": count, "max": settings.max_files_per_owner},
                )
        if settings.max_bytes_per_owner:
            used = self._files.bytes_by_owner(owner)
            if used + size > settings.max_bytes_per_owner:
                raise QuotaExceededError(
                    f"owner {owner!r} would exceed the storage byte limit",
                    details={"owner": owner, "used": used, "size": size, "max": settings.max_bytes_per_owner},
                )

    def _audited(self, op: str, sid: str | None, owner: str, err: Exception | None = None) -> None:
        if self._audit is None:
            return
        if err is None:
            self._audit.log(op, resource_type="upload", resource_id=sid, owner=owner)
        else:
            code = err.code if isinstance(err, RESCSError) else type(err).__name__
            self._audit.log(op, resource_type="upload", resource_id=sid, owner=owner,
                            outcome="denied" if code in ("UNAUTHORIZED", "FORBIDDEN") else "error",
                            error_code=code)

    def create(
        self,
        *,
        owner: str,
        filename: str,
        content_type: str = "application/octet-stream",
        total_size: int,
        chunk_size: int = DEFAULT_CHUNK,
        checksum: str | None = None,
        metadata: dict | None = None,
        tags: list[str] | None = None,
        actor: str = "system",
    ) -> UploadSessionData:
        try:
            if total_size < 0:
                raise InvalidRequestError("total_size must be >= 0", details={"total_size": total_size})
            if not (MIN_CHUNK <= chunk_size <= MAX_CHUNK):
                raise InvalidRequestError(
                    f"chunk_size must be {MIN_CHUNK}..{MAX_CHUNK}",
                    details={"chunk_size": chunk_size},
                )
            max_file = self._settings.max_file_size if self._settings else 0
            if max_file and total_size > max_file:
                raise PayloadTooLargeError(f"total_size exceeds maximum {max_file}", details={"size": total_size, "max": max_file})
            norm_tags = normalize_tags(tags or [])
            validate_tags(norm_tags)
            now = utcnow()
            session = UploadSessionData(
                id=str(uuid.uuid4()),
                owner=owner,
                filename=filename or "unnamed",
                content_type=content_type or "application/octet-stream",
                total_size=total_size,
                received_bytes=0,
                chunk_size=chunk_size,
                status="active",
                checksum=checksum,
                created_at=now,
                updated_at=now,
                expires_at=now + timedelta(seconds=MAX_SESSION_SECONDS),
                metadata=metadata or {},
                tags=norm_tags,
            )
            created = self._sessions.create(session)
            self._audited("upload.create", created.id, owner)
            return created
        except Exception as exc:
            self._audited("upload.create", None, owner, exc)
            raise

    def get(self, session_id: str) -> UploadSessionData:
        session = self._sessions.get(session_id)
        if session.status != "active" or session.is_expired():
            if session.status == "active" and session.is_expired():
                session.status = "expired"
                try:
                    self._sessions.update(session)
                except NotFoundError:
                    pass
            raise NotFoundError("upload session expired or closed", details={"id": session_id})
        return session

    def put_chunk(self, session_id: str, offset: int, data: bytes, *, actor: str = "system") -> UploadSessionData:
        try:
            session = self.get(session_id)
            self._check_owner_locked(session.owner)
            if not data:
                raise InvalidRequestError("chunk must not be empty", details={"offset": offset})
            if offset < 0 or offset + len(data) > session.total_size:
                raise InvalidRequestError("chunk outside declared size", details={"offset": offset, "size": len(data), "total": session.total_size})
            is_final = offset + len(data) == session.total_size
            if not is_final and len(data) != session.chunk_size:
                raise InvalidRequestError(
                    "intermediate chunks must equal chunk_size; only the final chunk may be smaller",
                    details={"offset": offset, "size": len(data), "chunk_size": session.chunk_size},
                )
            if len(data) > MAX_CHUNK:
                raise InvalidRequestError("chunk too large", details={"size": len(data)})
            key = _chunk_key(session_id, offset)
            # Duplicate chunk protection: identical offset+bytes is idempotent.
            if self._store.exists(key):
                existing = self._store.get(key)
                if existing == data:
                    return session
                # Conflicting overlapping chunk.
                raise ConflictError("conflicting chunk at offset", details={"offset": offset})
            # Overlap with different offsets is prevented by exact-offset keys;
            # partial overlaps would create gaps detected at finalize.
            self._store.put(key, data)
            # Recompute received bytes by scanning expected offsets (bounded: total/chunk).
            received = self._received(session)
            session.received_bytes = received
            session.updated_at = utcnow()
            updated = self._sessions.update(session)
            self._audited("upload.chunk", session_id, session.owner)
            return updated
        except Exception as exc:
            owner = actor
            try:
                owner = self._sessions.get(session_id).owner
            except Exception:
                pass
            self._audited("upload.chunk", session_id, owner, exc)
            raise

    def _received(self, session: UploadSessionData) -> int:
        # Sum contiguous bytes from offset 0 using stored chunk keys.
        # Chunks are fixed except possibly the last; walk offsets.
        received = 0
        offset = 0
        while offset < session.total_size:
            key = _chunk_key(session.id, offset)
            if not self._store.exists(key):
                break
            size = self._store.size(key)
            received += size
            if size == 0:
                break
            offset += size
            if offset > session.total_size:
                break
        return min(received, session.total_size)

    def finalize(self, session_id: str, *, actor: str = "system") -> FileObjectData:
        lock = self._finalize_lock(session_id)
        # Single-winner: in-process lock fast-path + DB-level conditional
        # status update, so concurrent finalizes are safe across processes.
        with lock:
            file_id: str | None = None
            try:
                session = self._sessions.get(session_id)
                self._check_owner_locked(session.owner)
                if session.status != "active":
                    raise ConflictError(
                        "upload session already finalized or closed",
                        details={"id": session_id, "status": session.status},
                    )
                if session.is_expired():
                    session.status = "expired"
                    try:
                        self._sessions.update(session)
                    except NotFoundError:
                        pass
                    raise NotFoundError("upload session expired", details={"id": session_id})
                # Atomic CAS active -> finalizing: only one finalizer wins,
                # in this process or any other. No blob write before winning.
                try:
                    won = self._sessions.compare_and_set_status(
                        session_id, "active", "finalizing"
                    )
                except NotFoundError:
                    raise ConflictError("upload session closed concurrently", details={"id": session_id})
                if not won:
                    try:
                        current = self._sessions.get(session_id)
                    except NotFoundError:
                        raise NotFoundError("upload session expired", details={"id": session_id})
                    raise ConflictError(
                        "upload session already finalized or closed",
                        details={"id": session_id, "status": current.status},
                    )
                session = self._sessions.get(session_id)
                # Pre-validate contiguous layout via sizes only (no byte buffering).
                layout: list[tuple[str, int]] = []
                offset = 0
                while offset < session.total_size:
                    key = _chunk_key(session.id, offset)
                    if not self._store.exists(key):
                        raise InvalidRequestError("missing chunk; upload incomplete", details={"offset": offset})
                    size = self._store.size(key)
                    if size <= 0 or offset + size > session.total_size:
                        raise InvalidRequestError("chunk exceeds declared size", details={"offset": offset})
                    layout.append((key, size))
                    offset += size
                if offset != session.total_size:
                    raise InvalidRequestError(
                        "incomplete upload", details={"received": offset, "total": session.total_size}
                    )
                # Governance before any blob write (no quota bypass via uploads).
                self._check_finalize_governance(session.owner, session.total_size, session.metadata)
                # Stream chunks -> hash incrementally -> object-store streaming write.
                digest = hashlib.sha256()

                def _stream() -> Iterator[bytes]:
                    for key, _size in layout:
                        for piece in self._store.get_stream(key):
                            if piece:
                                digest.update(piece)
                                yield piece

                file_id = str(uuid.uuid4())
                try:
                    self._store.put_stream(file_id, _stream())
                except Exception:
                    try:
                        self._store.delete(file_id)
                    except Exception:
                        pass
                    raise
                hex_digest = digest.hexdigest()
                if session.checksum and session.checksum.lower() != hex_digest.lower():
                    try:
                        self._store.delete(file_id)
                    except Exception:
                        pass
                    # Leave session active so the client can inspect/retry or cancel.
                    session.status = "active"
                    session.updated_at = utcnow()
                    try:
                        self._sessions.update(session)
                    except NotFoundError:
                        pass
                    raise InvalidRequestError("checksum mismatch", details={"expected": session.checksum, "actual": hex_digest})
                now = utcnow()
                file_obj = FileObjectData(
                    id=file_id,
                    filename=session.filename,
                    mime_type=session.content_type,
                    size=session.total_size,
                    storage_path=file_id,
                    sha256=hex_digest,
                    metadata=dict(session.metadata),
                    owner=session.owner,
                    version=1,
                    etag=file_etag(hex_digest, session.total_size),
                    created_at=now,
                    updated_at=now,
                    tags=list(session.tags),
                )
                try:
                    created = self._files.create(file_obj)
                except Exception:
                    try:
                        self._store.delete(file_id)
                    except Exception:
                        pass
                    session.status = "active"
                    session.updated_at = utcnow()
                    try:
                        self._sessions.update(session)
                    except NotFoundError:
                        pass
                    raise
                # Post-write race guard (mirrors FileService): loser rolls back.
                settings = self._settings
                if settings is not None and (
                    settings.max_files_per_owner or settings.max_bytes_per_owner
                ):
                    over = False
                    if settings.max_files_per_owner and self._files.count_by_owner(session.owner) > settings.max_files_per_owner:
                        over = True
                    if not over and settings.max_bytes_per_owner and self._files.bytes_by_owner(session.owner) > settings.max_bytes_per_owner:
                        over = True
                    if over:
                        try:
                            self._files.delete(created.id)
                        except Exception:
                            pass
                        try:
                            self._store.delete(file_id)
                        except Exception:
                            pass
                        session.status = "active"
                        session.updated_at = utcnow()
                        try:
                            self._sessions.update(session)
                        except NotFoundError:
                            pass
                        raise QuotaExceededError(
                            f"owner {session.owner!r} exceeded storage quota",
                            details={"owner": session.owner},
                        )
                session.status = "finalized"
                session.received_bytes = session.total_size
                session.updated_at = utcnow()
                try:
                    self._sessions.update(session)
                except NotFoundError:
                    pass
                self._cleanup_chunks(session.id, session.total_size)
                try:
                    self._sessions.delete(session.id)
                except NotFoundError:
                    pass
                self._audited("upload.finalize", session_id, session.owner)
                return created
            except Exception as exc:
                owner = actor
                try:
                    owner = self._sessions.get(session_id).owner
                except Exception:
                    pass
                self._audited("upload.finalize", session_id, owner, exc)
                raise
            finally:
                with self._locks_guard:
                    self._finalize_locks.pop(session_id, None)

    def cancel(self, session_id: str, *, actor: str = "system") -> None:
        try:
            session = self._sessions.get(session_id)
            self._check_owner_locked(session.owner)
            self._cleanup_chunks(session.id, session.total_size)
            try:
                self._sessions.delete(session.id)
            except NotFoundError:
                pass
            self._audited("upload.cancel", session_id, session.owner)
        except Exception as exc:
            self._audited("upload.cancel", session_id, actor, exc)
            raise

    def _cleanup_chunks(self, session_id: str, total_size: int) -> None:
        # Remove all chunk keys that may exist (bounded iterations).
        offset = 0
        # Walk by probing: try offsets in steps; also attempt direct prefix scan for local store.
        # Simple approach: iterate offsets 0..total in chunk increments is unknown; instead
        # try to delete keys by scanning: we stored exact offsets, so probe sequentially.
        # To avoid infinite loop on sparse offsets, cap iterations.
        seen_empty = 0
        while offset <= total_size and seen_empty < 3:
            key = _chunk_key(session_id, offset)
            if self._store.exists(key):
                try:
                    size = self._store.size(key)
                except Exception:
                    size = 0
                self._store.delete(key)
                offset += max(size, 1)
                seen_empty = 0
            else:
                # Advance by 1 to catch unaligned offsets? Use chunk scan fallback:
                # list local dir prefix if available.
                advanced = self._advance_probe(session_id, offset)
                if advanced is None:
                    break
                offset = advanced
                seen_empty += 1

    def _advance_probe(self, session_id: str, offset: int) -> int | None:
        # Generic fallback: try next plausible offsets by scanning store if it exposes listing.
        store = self._store
        prefix = f"{session_id}__chunk__"
        try:
            # Escape glob metachars in session_id-derived prefix (*?[]).
            import re as _re

            safe_prefix = _re.sub(r"([*?\[\]])", r"[\1]", prefix)
            base = getattr(store, "_base", None)
            if base is not None:
                from pathlib import Path
                found: list[int] = []
                for p in Path(base).glob(safe_prefix + "*"):
                    try:
                        off = int(p.name.split("__chunk__")[1])
                        if off > offset:
                            found.append(off)
                    except (ValueError, IndexError):
                        continue
                return min(found) if found else None
            blobs = getattr(store, "_blobs", None)
            if isinstance(blobs, dict):
                found = []
                for k in blobs.keys():
                    if k.startswith(prefix):
                        try:
                            off = int(k.split("__chunk__")[1])
                            if off > offset:
                                found.append(off)
                        except (ValueError, IndexError):
                            continue
                return min(found) if found else None
        except Exception:
            return None
        return None

    def cleanup_expired(self, *, actor: str = "system", limit: int = 500) -> int:
        expired = self._sessions.list_expired(utcnow(), limit=limit)
        count = 0
        for session in expired:
            try:
                self._cleanup_chunks(session.id, session.total_size)
                self._sessions.delete(session.id)
                count += 1
            except NotFoundError:
                continue
        if self._audit is not None:
            self._audit.log("upload.cleanup", resource_type="upload", owner=actor)
        return count

