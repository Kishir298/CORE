"""Storage abstraction: repository interfaces (protocols).

The service layer depends only on these protocols. Concrete backends
(in-memory, SQLAlchemy) implement them; future backends can too without
touching the application core.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from rescs.domain import AuditData, FileObjectData, Page, RecordData, UploadSessionData


@runtime_checkable
class RecordRepository(Protocol):
    def create(self, record: RecordData) -> RecordData: ...

    def get(self, record_id: str) -> RecordData: ...
    """Return a live, non-expired record; deleted/expired -> NotFoundError."""

    def get_including_deleted(self, record_id: str) -> RecordData: ...
    """Return the record regardless of deletion/expiry state."""

    def get_by_namespace_key(self, namespace: str, key: str) -> RecordData | None: ...
    """Return the live, non-expired occupant of (namespace, key), if any."""

    def find_occupant(self, namespace: str, key: str) -> RecordData | None: ...
    """Return any occupant of (namespace, key), including deleted/expired."""

    def update(self, record: RecordData) -> RecordData: ...

    def delete(self, record_id: str) -> None: ...
    """Hard delete (purge)."""

    def find_by_idempotency_key(self, idempotency_key: str) -> RecordData | None: ...

    def list(
        self,
        namespace: str | None = None,
        key_prefix: str | None = None,
        owner: str | None = None,
        limit: int = 100,
        offset: int = 0,
        tags: list[str] | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        updated_after: datetime | None = None,
        updated_before: datetime | None = None,
        include_deleted: bool = False,
        include_expired: bool = False,
    ) -> Page[RecordData]: ...

    def list_deleted(
        self,
        namespace: str | None = None,
        owner: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Page[RecordData]: ...

    def list_expired(
        self, before: datetime, limit: int = 100
    ) -> list[RecordData]: ...

    def search(
        self,
        query: str,
        namespace: str | None = None,
        owner: str | None = None,
        limit: int = 100,
        offset: int = 0,
        tags: list[str] | None = None,
        include_deleted: bool = False,
        include_expired: bool = False,
    ) -> Page[RecordData]: ...

    def count_by_owner(
        self, owner: str, *, include_deleted: bool = False
    ) -> int: ...
    """Live, non-expired record count for quota accounting."""


@runtime_checkable
class FileObjectRepository(Protocol):
    def create(self, file_object: FileObjectData) -> FileObjectData: ...

    def get(self, file_id: str) -> FileObjectData: ...
    """Return a live, non-expired file; deleted/expired -> NotFoundError."""

    def get_including_deleted(self, file_id: str) -> FileObjectData: ...

    def update(self, file_object: FileObjectData) -> FileObjectData: ...

    def delete(self, file_id: str) -> None: ...
    """Hard delete (purge)."""

    def find_by_idempotency_key(self, idempotency_key: str) -> FileObjectData | None: ...

    def list(
        self,
        owner: str | None = None,
        limit: int = 100,
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
    ) -> Page[FileObjectData]: ...

    def list_deleted(
        self,
        owner: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Page[FileObjectData]: ...

    def list_expired(
        self, before: datetime, limit: int = 100
    ) -> list[FileObjectData]: ...

    def count_by_owner(
        self, owner: str, *, include_deleted: bool = False
    ) -> int: ...

    def bytes_by_owner(
        self, owner: str, *, include_deleted: bool = False
    ) -> int: ...


@runtime_checkable
class AuditRepository(Protocol):
    def append(self, event: AuditData) -> AuditData: ...

    def list(
        self,
        owner: str | None = None,
        operation: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Page[AuditData]: ...

    def prune_before(self, cutoff: datetime) -> int: ...


@runtime_checkable
class UploadSessionRepository(Protocol):
    def create(self, session: UploadSessionData) -> UploadSessionData: ...

    def get(self, session_id: str) -> UploadSessionData: ...

    def update(self, session: UploadSessionData) -> UploadSessionData: ...

    def compare_and_set_status(self, session_id: str, expect: str, new: str) -> bool:
        """Atomically transition status expect -> new.

        Returns True when transitioned, False when present but status
        differs. Missing id raises NotFoundError (preserves 404 vs 409).
        """
        ...

    def delete(self, session_id: str) -> None: ...

    def list_expired(self, before: datetime, limit: int = 100) -> list[UploadSessionData]: ...
