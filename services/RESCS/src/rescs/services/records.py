"""Record storage service: CREATE, READ, UPDATE, DELETE, LIST, SEARCH.

The service is the single entry point used by the API layer. It validates
inputs (done at the schema boundary), performs the operation through a
repository, and returns domain objects. Every predictable failure raises a
domain error; callers never see repository or database exceptions.

v0.2 additions: soft delete / restore / purge, TTL expiry, tags, bulk
operations, quotas, expiry cleanup. Expired resources behave as absent for
ordinary operations; writes transparently reclaim expired occupants.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from rescs.config import Settings
from rescs.domain import (
    Page,
    RecordData,
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
)
from rescs.etag import content_etag
from rescs.interfaces.repository import RecordRepository
from rescs.schemas.record import RecordCreate, RecordUpdate
from rescs.services.audit import AuditService
from rescs.services.expiry import resolve_expiry
from rescs.services.utils import clamp_pagination

DEFAULT_LIMIT = 100


def _check_etag(existing: RecordData, expected_etag: str | None) -> None:
    if expected_etag is not None and existing.etag != expected_etag:
        raise PreconditionFailedError(
            "etag does not match current record state",
            details={
                "id": existing.id,
                "expected_etag": expected_etag,
                "current_etag": existing.etag,
                "version": existing.version,
            },
        )


class RecordService:
    def __init__(
        self,
        repository: RecordRepository,
        *,
        settings: Settings | None = None,
        audit: AuditService | None = None,
    ) -> None:
        self._repo = repository
        self._settings = settings
        self._audit = audit

    # -- internal helpers -------------------------------------------------

    def _audited(self, operation: str, record: RecordData | None, error: Exception | None = None, owner: str = "system") -> None:
        if self._audit is None:
            return
        resource_id = record.id if record else None
        resource_owner = record.owner if record else owner
        if error is None:
            self._audit.log(
                operation,
                resource_type="record",
                resource_id=resource_id,
                owner=resource_owner,
            )
        else:
            code = error.code if isinstance(error, RESCSError) else type(error).__name__
            self._audit.log(
                operation,
                resource_type="record",
                resource_id=resource_id,
                owner=resource_owner,
                outcome="denied" if code in ("UNAUTHORIZED", "FORBIDDEN") else "error",
                error_code=code,
            )

    def _check_metadata_size(self, metadata: dict) -> None:
        if self._settings is None:
            return
        size = len(json.dumps(metadata, default=str))
        if self._settings.max_metadata_bytes and size > self._settings.max_metadata_bytes:
            raise PayloadTooLargeError(
                f"metadata exceeds {self._settings.max_metadata_bytes} bytes",
                details={"size": size, "max": self._settings.max_metadata_bytes},
            )

    def _check_quota(self, owner: str) -> None:
        if self._settings is None or not self._settings.max_records_per_owner:
            return
        count = self._repo.count_by_owner(owner)
        if count >= self._settings.max_records_per_owner:
            raise QuotaExceededError(
                f"owner {owner!r} reached the record limit",
                details={
                    "owner": owner,
                    "count": count,
                    "max": self._settings.max_records_per_owner,
                },
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

    def _reclaim_expired_occupant(self, namespace: str, key: str) -> None:
        """Hard-remove an expired (not deleted) occupant so a write can proceed."""
        occupant = self._repo.find_occupant(namespace, key)
        if occupant is not None and occupant.deleted_at is None and occupant.is_expired():
            self._repo.delete(occupant.id)

    def _check_bulk_owner(self, resource_owner: str) -> None:
        """Enforce single-owner lock inside bulk batches (per-item 403)."""
        from rescs.errors import ForbiddenError

        from rescs.gateway_scope import current_owner
        locked = current_owner.get() or (self._settings.api_key_owner if self._settings else "")
        if locked and resource_owner != locked:
            raise ForbiddenError(
                f"this resource belongs to owner {resource_owner!r}",
                details={"owner": resource_owner},
            )

    # -- create / upsert / read / update -----------------------------------

    def create(self, payload: RecordCreate, *, actor: str = "system") -> RecordData:
        try:
            tags = normalize_tags(payload.tags)
            validate_tags(tags)
            self._check_metadata_size(payload.metadata)
            expires_at = self._resolve_expiry(payload.expires_at, payload.ttl_seconds)
            if payload.idempotency_key is not None:
                existing = self._repo.find_by_idempotency_key(payload.idempotency_key)
                if existing is not None:
                    self._check_bulk_owner(existing.owner)
                    if existing.owner != payload.owner:
                        from rescs.errors import ForbiddenError
                        raise ForbiddenError("idempotency owner mismatch", details={})
                    if existing.deleted_at is not None:
                        raise ConflictError(
                            "idempotency key belongs to a deleted record;"
                            " purge it or use a new key",
                            details={"idempotency_key": payload.idempotency_key},
                        )
                    if existing.is_expired():
                        self._repo.delete(existing.id)
                    else:
                        return existing
            self._reclaim_expired_occupant(payload.namespace, payload.key)
            self._check_quota(payload.owner)
            now = utcnow()
            record = RecordData(
                id=str(uuid.uuid4()),
                namespace=payload.namespace,
                key=payload.key,
                value=payload.value,
                metadata=payload.metadata,
                owner=payload.owner,
                version=1,
                idempotency_key=payload.idempotency_key,
                etag=content_etag(payload.value, payload.metadata, tags),
                created_at=now,
                updated_at=now,
                tags=tags,
                expires_at=expires_at,
            )
            created = self._repo.create(record)
            # Post-write race guard: two concurrent creates may both pass the
            # pre-check; the loser rolls back so quotas stay race-safe.
            if self._settings is not None and self._settings.max_records_per_owner:
                count = self._repo.count_by_owner(payload.owner)
                if count > self._settings.max_records_per_owner:
                    try:
                        self._repo.delete(created.id)
                    except Exception:
                        pass
                    raise QuotaExceededError(
                        f"owner {payload.owner!r} reached the record limit",
                        details={"owner": payload.owner, "count": count, "max": self._settings.max_records_per_owner},
                    )
            self._audited("record.create", created)
            return created
        except Exception as exc:
            self._audited("record.create", None, exc, owner=payload.owner)
            raise

    def put(
        self,
        payload: RecordCreate,
        *,
        actor: str = "system",
        expected_etag: str | None = None,
    ) -> RecordData:
        """Create or replace the record identified by (namespace, key)."""
        try:
            existing = self._repo.get_by_namespace_key(payload.namespace, payload.key)
            self._check_bulk_owner(payload.owner)
            if existing is not None and existing.owner != payload.owner:
                from rescs.errors import ForbiddenError
                raise ForbiddenError("record owner mismatch", details={})
            if existing is None:
                if expected_etag is not None:
                    raise PreconditionFailedError(
                        "record does not exist; cannot match If-Match",
                        details={"namespace": payload.namespace, "key": payload.key},
                    )
                return self.create(payload, actor=actor)
            _check_etag(existing, expected_etag)
            tags = normalize_tags(payload.tags)
            validate_tags(tags)
            self._check_metadata_size(payload.metadata)
            expires_at = self._resolve_expiry(payload.expires_at, payload.ttl_seconds)
            updated = RecordData(
                id=existing.id,
                namespace=payload.namespace,
                key=payload.key,
                value=payload.value,
                metadata=payload.metadata,
                owner=payload.owner,
                version=existing.version + 1,
                idempotency_key=existing.idempotency_key or payload.idempotency_key,
                etag=content_etag(payload.value, payload.metadata, tags),
                created_at=existing.created_at,
                updated_at=utcnow(),
                tags=tags,
                expires_at=expires_at,
            )
            replaced = self._repo.update(updated)
            self._audited("record.put", replaced)
            return replaced
        except Exception as exc:
            self._audited("record.put", None, exc, owner=payload.owner)
            raise

    def get(self, record_id: str, *, actor: str = "system") -> RecordData:
        return self._repo.get(record_id)

    def get_including_deleted(
        self, record_id: str, *, actor: str = "system"
    ) -> RecordData:
        """Fetch regardless of deletion/expiry (recovery/admin paths)."""
        return self._repo.get_including_deleted(record_id)

    def update(
        self,
        record_id: str,
        payload: RecordUpdate,
        *,
        actor: str = "system",
        expected_etag: str | None = None,
    ) -> RecordData:
        try:
            existing = self._repo.get(record_id)
            _check_etag(existing, expected_etag)
            fields = (
                payload.value,
                payload.metadata,
                payload.namespace,
                payload.key,
                payload.tags,
                payload.expires_at,
                payload.ttl_seconds,
            )
            if all(field is None for field in fields):
                raise InvalidRequestError(
                    "no fields to update", details={"id": record_id}
                )
            tags = normalize_tags(payload.tags) if payload.tags is not None else existing.tags
            validate_tags(tags)
            metadata = payload.metadata if payload.metadata is not None else existing.metadata
            self._check_metadata_size(metadata)
            value = payload.value if payload.value is not None else existing.value
            if payload.expires_at is not None or payload.ttl_seconds is not None:
                expires_at = self._resolve_expiry(
                    payload.expires_at, payload.ttl_seconds
                )
            else:
                expires_at = existing.expires_at
            updated = RecordData(
                id=existing.id,
                namespace=payload.namespace if payload.namespace is not None else existing.namespace,
                key=payload.key if payload.key is not None else existing.key,
                value=value,
                metadata=metadata,
                owner=existing.owner,
                version=existing.version + 1,
                idempotency_key=existing.idempotency_key,
                etag=content_etag(value, metadata, tags),
                created_at=existing.created_at,
                updated_at=utcnow(),
                tags=tags,
                expires_at=expires_at,
            )
            result = self._repo.update(updated)
            self._audited("record.update", result)
            return result
        except Exception as exc:
            self._audited("record.update", None, exc)
            raise

    # -- soft delete / restore / purge --------------------------------------

    def delete(
        self,
        record_id: str,
        *,
        actor: str = "system",
        expected_etag: str | None = None,
    ) -> None:
        """Soft-delete: the tombstone keeps metadata but hides the resource."""
        target: RecordData | None = None
        try:
            target = self._repo.get(record_id)
            _check_etag(target, expected_etag)
            existing = target
            tombstone = RecordData(
                id=existing.id,
                namespace=existing.namespace,
                key=existing.key,
                value=existing.value,
                metadata=existing.metadata,
                owner=existing.owner,
                version=existing.version + 1,
                idempotency_key=existing.idempotency_key,
                etag=existing.etag,
                created_at=existing.created_at,
                updated_at=utcnow(),
                tags=existing.tags,
                expires_at=existing.expires_at,
                deleted_at=utcnow(),
                deleted_by=actor,
            )
            self._repo.update(tombstone)
            self._audited("record.delete", tombstone)
        except Exception as exc:
            self._audited("record.delete", target, exc)
            raise

    def restore(
        self,
        record_id: str,
        *,
        actor: str = "system",
        expected_etag: str | None = None,
    ) -> RecordData:
        target: RecordData | None = None
        try:
            target = self._repo.get_including_deleted(record_id)
            existing = target
            if existing.deleted_at is None:
                raise InvalidRequestError(
                    "record is not deleted", details={"id": record_id}
                )
            _check_etag(existing, expected_etag)
            occupant = self._repo.get_by_namespace_key(existing.namespace, existing.key)
            if occupant is not None and occupant.id != existing.id:
                raise ConflictError(
                    "a live record already uses this namespace/key",
                    details={
                        "namespace": existing.namespace,
                        "key": existing.key,
                        "occupant_id": occupant.id,
                    },
                )
            restored = RecordData(
                id=existing.id,
                namespace=existing.namespace,
                key=existing.key,
                value=existing.value,
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
            self._audited("record.restore", result)
            return result
        except Exception as exc:
            self._audited("record.restore", target, exc)
            raise

    def purge(
        self,
        record_id: str,
        *,
        actor: str = "system",
        expected_etag: str | None = None,
    ) -> None:
        """Permanently remove a record (tombstone or live)."""
        target: RecordData | None = None
        try:
            target = self._repo.get_including_deleted(record_id)
            _check_etag(target, expected_etag)
            self._repo.delete(record_id)
            self._audited("record.purge", target)
        except Exception as exc:
            self._audited("record.purge", target, exc)
            raise

    # -- listing / search -----------------------------------------------------

    def list(
        self,
        actor: str = "system",
        *,
        namespace: str | None = None,
        key_prefix: str | None = None,
        owner: str | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        tags: list[str] | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        updated_after: datetime | None = None,
        updated_before: datetime | None = None,
        include_deleted: bool = False,
        include_expired: bool = False,
    ) -> Page[RecordData]:
        limit, offset = clamp_pagination(limit, offset)
        return self._repo.list(
            namespace=namespace,
            key_prefix=key_prefix,
            owner=owner,
            limit=limit,
            offset=offset,
            tags=tags,
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
        namespace: str | None = None,
        owner: str | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> Page[RecordData]:
        limit, offset = clamp_pagination(limit, offset)
        return self._repo.list_deleted(
            namespace=namespace, owner=owner, limit=limit, offset=offset
        )

    def search(
        self,
        actor: str = "system",
        *,
        query: str,
        namespace: str | None = None,
        owner: str | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        tags: list[str] | None = None,
        include_deleted: bool = False,
        include_expired: bool = False,
    ) -> Page[RecordData]:
        limit, offset = clamp_pagination(limit, offset)
        return self._repo.search(
            query=query,
            namespace=namespace,
            owner=owner,
            limit=limit,
            offset=offset,
            tags=tags,
            include_deleted=include_deleted,
            include_expired=include_expired,
        )

    # -- bulk ------------------------------------------------------------------

    def bulk(
        self, operations: list[dict[str, Any]], *, actor: str = "system"
    ) -> list[dict[str, Any]]:
        """Apply a bounded batch of per-item operations with explicit statuses.

        Partial success is intentional: each item yields its own status.
        Not atomic — successful items are not rolled back when a sibling
        fails. Owner isolation is enforced per item in locked mode.
        """
        batch_max = self._settings.max_bulk_batch if self._settings else 100
        if len(operations) > batch_max:
            raise InvalidRequestError(
                f"bulk batch exceeds maximum of {batch_max}",
                details={"count": len(operations), "max": batch_max},
            )
        results: list[dict[str, Any]] = []
        for index, operation in enumerate(operations):
            op = operation.get("op")
            try:
                if op == "create":
                    record = self.create(RecordCreate(**operation["record"]), actor=actor)
                    results.append({"index": index, "status": "created", "id": record.id})
                elif op == "put":
                    record = self.put(
                        RecordCreate(**operation["record"]),
                        actor=actor,
                        expected_etag=operation.get("if_match"),
                    )
                    results.append({"index": index, "status": "put", "id": record.id})
                elif op == "delete":
                    target = self._repo.get(operation["id"])
                    self._check_bulk_owner(target.owner)
                    self.delete(
                        operation["id"],
                        actor=actor,
                        expected_etag=operation.get("if_match"),
                    )
                    results.append({"index": index, "status": "deleted", "id": operation["id"]})
                elif op == "restore":
                    target = self._repo.get_including_deleted(operation["id"])
                    self._check_bulk_owner(target.owner)
                    record = self.restore(
                        operation["id"],
                        actor=actor,
                        expected_etag=operation.get("if_match"),
                    )
                    results.append({"index": index, "status": "restored", "id": record.id})
                elif op == "purge":
                    target = self._repo.get_including_deleted(operation["id"])
                    self._check_bulk_owner(target.owner)
                    self.purge(
                        operation["id"],
                        actor=actor,
                        expected_etag=operation.get("if_match"),
                    )
                    results.append({"index": index, "status": "purged", "id": operation["id"]})
                else:
                    results.append(
                        {
                            "index": index,
                            "status": "error",
                            "code": "INVALID_REQUEST",
                            "message": f"unknown bulk op {op!r}",
                        }
                    )
            except RESCSError as exc:
                results.append(
                    {
                        "index": index,
                        "status": "error",
                        "code": exc.code,
                        "message": exc.message,
                        "details": exc.details,
                    }
                )
            except ValueError as exc:
                results.append(
                    {
                        "index": index,
                        "status": "error",
                        "code": "INVALID_REQUEST",
                        "message": str(exc),
                    }
                )
        self._audited_bulk(len(operations), actor)
        return results

    def _audited_bulk(self, count: int, actor: str) -> None:
        if self._audit is None:
            return
        self._audit.log(
            "record.bulk", resource_type="record", owner=actor,
        )

    # -- expiry cleanup ----------------------------------------------------------

    def count_expired(self, *, limit: int = 500) -> int:
        """Number of expired records awaiting cleanup (bounded preview)."""
        return len(self._repo.list_expired(utcnow(), limit=limit))

    def cleanup_expired(self, *, actor: str = "system", limit: int = 500) -> int:
        """Purge expired records; returns the number purged."""
        now = utcnow()
        expired = self._repo.list_expired(now, limit=limit)
        purged = 0
        for item in expired:
            try:
                self._repo.delete(item.id)
                purged += 1
            except NotFoundError:
                continue
        if self._audit is not None:
            self._audit.log(
                "record.cleanup",
                resource_type="record",
                owner=actor,
            )
        return purged

