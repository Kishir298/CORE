"""In-memory repository backends.

Deterministic, dependency-free implementations used by unit tests and as the
reference behaviour for the repository protocol. Data is lost on process
exit; they are never used for real persistence.
"""

from __future__ import annotations

import json
import threading
from typing import Generic, TypeVar

from rescs.domain import (
    AuditData,
    FileObjectData,
    Page,
    RecordData,
    UploadSessionData,
    ensure_utc,
    utcnow,
)
from rescs.errors import ConflictError, NotFoundError

T = TypeVar("T", RecordData, FileObjectData)


class _InMemoryStore(Generic[T]):
    def __init__(self) -> None:
        self._items: dict[str, T] = {}
        self._namespace_keys: dict[tuple[str, str], str] = {}
        self._idempotency: dict[str, str] = {}
        self._lock = threading.RLock()

    def create(self, item: T, namespace: str | None = None, key: str | None = None) -> T:
        with self._lock:
            if item.id in self._items:
                raise ConflictError("item already exists", details={"id": item.id})
            if namespace is not None and key is not None:
                natural = (namespace, key)
                if natural in self._namespace_keys:
                    raise ConflictError(
                        "item already exists for namespace/key",
                        details={"namespace": namespace, "key": key},
                    )
            if item.idempotency_key and item.idempotency_key in self._idempotency:
                raise ConflictError(
                    "idempotency key already used",
                    details={"idempotency_key": item.idempotency_key},
                )
            self._items[item.id] = item
            if namespace is not None and key is not None:
                self._namespace_keys[(namespace, key)] = item.id
            if item.idempotency_key:
                self._idempotency[item.idempotency_key] = item.id
            return item

    def update(self, item: T, namespace: str | None = None, key: str | None = None) -> T:
        with self._lock:
            if item.id not in self._items:
                raise NotFoundError("item not found", details={"id": item.id})
            self._items[item.id] = item
            if namespace is not None and key is not None:
                for k, existing_id in list(self._namespace_keys.items()):
                    if existing_id == item.id and k != (namespace, key):
                        del self._namespace_keys[k]
                self._namespace_keys[(namespace, key)] = item.id
            if item.idempotency_key:
                old = self._idempotency.get(item.idempotency_key)
                if old is not None and old != item.id:
                    raise ConflictError(
                        "idempotency key already used",
                        details={"idempotency_key": item.idempotency_key},
                    )
                self._idempotency[item.idempotency_key] = item.id
            return item

    def delete(self, item_id: str) -> None:
        with self._lock:
            item = self._items.get(item_id)
            if item is None:
                raise NotFoundError("item not found", details={"id": item_id})
            self._namespace_keys = {
                k: v for k, v in self._namespace_keys.items() if v != item_id
            }
            self._idempotency = {
                k: v for k, v in self._idempotency.items() if v != item_id
            }
            del self._items[item_id]

    def get(self, item_id: str) -> T:
        with self._lock:
            item = self._items.get(item_id)
            if item is None:
                raise NotFoundError("item not found", details={"id": item_id})
            return item

    def get_by_natural_key(self, namespace: str, key: str) -> T | None:
        with self._lock:
            item_id = self._namespace_keys.get((namespace, key))
            if item_id is None:
                return None
            return self._items[item_id]

    def drop_natural(self, namespace: str, key: str) -> None:
        with self._lock:
            self._namespace_keys.pop((namespace, key), None)

    def find_by_idempotency_key(self, idempotency_key: str) -> T | None:
        with self._lock:
            item_id = self._idempotency.get(idempotency_key)
            if item_id is None:
                return None
            return self._items[item_id]

    def page(
        self,
        predicate,
        limit: int,
        offset: int,
    ) -> list[T]:
        with self._lock:
            items = [item for item in self._items.values() if predicate(item)]
            items.sort(key=lambda i: (i.updated_at, i.id))
            return items[offset : offset + limit]

    def count(self, predicate) -> int:
        with self._lock:
            return sum(1 for item in self._items.values() if predicate(item))


class InMemoryRecordRepository:
    def __init__(self) -> None:
        self._store: _InMemoryStore[RecordData] = _InMemoryStore()

    @staticmethod
    def _live(item: RecordData, now) -> bool:
        return item.deleted_at is None and not item.is_expired(now)

    def create(self, record: RecordData) -> RecordData:
        occupant = self._store.get_by_natural_key(record.namespace, record.key)
        if occupant is not None and not self._live(occupant, utcnow()):
            self._store.drop_natural(record.namespace, record.key)
        return self._store.create(record, record.namespace, record.key)

    def get(self, record_id: str) -> RecordData:
        item = self._store.get(record_id)
        if not self._live(item, utcnow()):
            raise NotFoundError("record not found", details={"id": record_id})
        return item

    def get_including_deleted(self, record_id: str) -> RecordData:
        return self._store.get(record_id)

    def get_by_namespace_key(self, namespace: str, key: str) -> RecordData | None:
        item = self._store.get_by_natural_key(namespace, key)
        if item is None or not self._live(item, utcnow()):
            return None
        return item

    def find_occupant(self, namespace: str, key: str) -> RecordData | None:
        return self._store.get_by_natural_key(namespace, key)

    def update(self, record: RecordData) -> RecordData:
        return self._store.update(record, record.namespace, record.key)

    def delete(self, record_id: str) -> None:
        self._store.delete(record_id)

    def find_by_idempotency_key(self, idempotency_key: str) -> RecordData | None:
        return self._store.find_by_idempotency_key(idempotency_key)

    def list(
        self,
        namespace: str | None = None,
        key_prefix: str | None = None,
        owner: str | None = None,
        limit: int = 100,
        offset: int = 0,
        tags: list[str] | None = None,
        created_after=None,
        created_before=None,
        updated_after=None,
        updated_before=None,
        include_deleted: bool = False,
        include_expired: bool = False,
    ) -> Page[RecordData]:
        now = utcnow()

        def predicate(r: RecordData) -> bool:
            if namespace is not None and r.namespace != namespace:
                return False
            if key_prefix is not None and not r.key.startswith(key_prefix):
                return False
            if owner is not None and r.owner != owner:
                return False
            if tags is not None and not set(tags) <= set(r.tags):
                return False
            if not _in_window(r.created_at, created_after, created_before):
                return False
            if not _in_window(r.updated_at, updated_after, updated_before):
                return False
            if not include_deleted and r.deleted_at is not None:
                return False
            if not include_expired and r.is_expired(now):
                return False
            return True

        items = self._store.page(predicate, limit, offset)
        return Page(
            items=items, total=self._store.count(predicate), limit=limit, offset=offset
        )

    def list_deleted(
        self,
        namespace: str | None = None,
        owner: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Page[RecordData]:
        predicate = lambda r: (
            r.deleted_at is not None
            and (namespace is None or r.namespace == namespace)
            and (owner is None or r.owner == owner)
        )
        items = self._store.page(predicate, limit, offset)
        return Page(
            items=items, total=self._store.count(predicate), limit=limit, offset=offset
        )

    def list_expired(self, before, limit: int = 100) -> list[RecordData]:
        utcnow()
        with self._store._lock:
            items = [
                item
                for item in self._store._items.values()
                if item.expires_at is not None
                and ensure_utc(item.expires_at) <= ensure_utc(before)
            ]
            items.sort(key=lambda i: (ensure_utc(i.expires_at), i.id))
            return items[:limit]

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
    ) -> Page[RecordData]:
        needle = query.lower()
        now = utcnow()

        def predicate(r: RecordData) -> bool:
            if namespace is not None and r.namespace != namespace:
                return False
            if owner is not None and r.owner != owner:
                return False
            if tags is not None and not set(tags) <= set(r.tags):
                return False
            if not include_deleted and r.deleted_at is not None:
                return False
            if not include_expired and r.is_expired(now):
                return False
            text = json.dumps(
                [r.value, r.metadata], sort_keys=True, default=str
            ).lower()
            return needle in r.key.lower() or needle in text

        items = self._store.page(predicate, limit, offset)
        return Page(
            items=items, total=self._store.count(predicate), limit=limit, offset=offset
        )

    def count_by_owner(self, owner: str, *, include_deleted: bool = False) -> int:
        now = utcnow()
        return self._store.count(
            lambda r: r.owner == owner
            and (include_deleted or r.deleted_at is None)
            and not r.is_expired(now)
        )


def _in_window(value, after, before) -> bool:
    moment = ensure_utc(value)
    if after is not None and moment < ensure_utc(after):
        return False
    if before is not None and moment >= ensure_utc(before):
        return False
    return True


class InMemoryFileObjectRepository:
    def __init__(self) -> None:
        self._store: _InMemoryStore[FileObjectData] = _InMemoryStore()

    @staticmethod
    def _live(item: FileObjectData, now) -> bool:
        return item.deleted_at is None and not item.is_expired(now)

    def create(self, file_object: FileObjectData) -> FileObjectData:
        return self._store.create(file_object)

    def get(self, file_id: str) -> FileObjectData:
        item = self._store.get(file_id)
        if not self._live(item, utcnow()):
            raise NotFoundError("file not found", details={"id": file_id})
        return item

    def get_including_deleted(self, file_id: str) -> FileObjectData:
        return self._store.get(file_id)

    def update(self, file_object: FileObjectData) -> FileObjectData:
        return self._store.update(file_object)

    def delete(self, file_id: str) -> None:
        self._store.delete(file_id)

    def find_by_idempotency_key(self, idempotency_key: str) -> FileObjectData | None:
        return self._store.find_by_idempotency_key(idempotency_key)

    def list(
        self,
        owner: str | None = None,
        limit: int = 100,
        offset: int = 0,
        tags: list[str] | None = None,
        mime_type: str | None = None,
        size_min: int | None = None,
        size_max: int | None = None,
        created_after=None,
        created_before=None,
        updated_after=None,
        updated_before=None,
        include_deleted: bool = False,
        include_expired: bool = False,
    ) -> Page[FileObjectData]:
        now = utcnow()

        def predicate(f: FileObjectData) -> bool:
            if owner is not None and f.owner != owner:
                return False
            if tags is not None and not set(tags) <= set(f.tags):
                return False
            if mime_type is not None and f.mime_type != mime_type:
                return False
            if size_min is not None and f.size < size_min:
                return False
            if size_max is not None and f.size > size_max:
                return False
            if not _in_window(f.created_at, created_after, created_before):
                return False
            if not _in_window(f.updated_at, updated_after, updated_before):
                return False
            if not include_deleted and f.deleted_at is not None:
                return False
            if not include_expired and f.is_expired(now):
                return False
            return True

        items = self._store.page(predicate, limit, offset)
        return Page(
            items=items, total=self._store.count(predicate), limit=limit, offset=offset
        )

    def list_deleted(
        self,
        owner: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Page[FileObjectData]:
        predicate = lambda f: f.deleted_at is not None and (
            owner is None or f.owner == owner
        )
        items = self._store.page(predicate, limit, offset)
        return Page(
            items=items, total=self._store.count(predicate), limit=limit, offset=offset
        )

    def list_expired(self, before, limit: int = 100) -> list[FileObjectData]:
        with self._store._lock:
            items = [
                item
                for item in self._store._items.values()
                if item.expires_at is not None
                and ensure_utc(item.expires_at) <= ensure_utc(before)
            ]
            items.sort(key=lambda i: (ensure_utc(i.expires_at), i.id))
            return items[:limit]

    def count_by_owner(self, owner: str, *, include_deleted: bool = False) -> int:
        now = utcnow()
        return self._store.count(
            lambda f: f.owner == owner
            and (include_deleted or f.deleted_at is None)
            and not f.is_expired(now)
        )

    def bytes_by_owner(self, owner: str, *, include_deleted: bool = False) -> int:
        now = utcnow()
        with self._store._lock:
            return sum(
                item.size
                for item in self._store._items.values()
                if item.owner == owner
                and (include_deleted or item.deleted_at is None)
                and not item.is_expired(now)
            )


class InMemoryAuditRepository:
    def __init__(self) -> None:
        self._events: dict[str, AuditData] = {}
        self._lock = threading.RLock()

    def append(self, event: AuditData) -> AuditData:
        with self._lock:
            if event.id in self._events:
                raise ConflictError("audit event already exists", details={"id": event.id})
            self._events[event.id] = event
            return event

    def list(
        self,
        owner: str | None = None,
        operation: str | None = None,
        since=None,
        limit: int = 100,
        offset: int = 0,
    ) -> Page[AuditData]:
        with self._lock:
            items = [
                event
                for event in self._events.values()
                if (owner is None or event.owner == owner)
                and (operation is None or event.operation == operation)
                and (since is None or ensure_utc(event.timestamp) >= ensure_utc(since))
            ]
            items.sort(key=lambda e: (ensure_utc(e.timestamp), e.id))
            total = len(items)
            return Page(items=items[offset : offset + limit], total=total, limit=limit, offset=offset)

    def prune_before(self, cutoff) -> int:
        moment = ensure_utc(cutoff)
        with self._lock:
            stale = [
                event_id
                for event_id, event in self._events.items()
                if ensure_utc(event.timestamp) < moment
            ]
            for event_id in stale:
                del self._events[event_id]
            return len(stale)


class InMemoryUploadSessionRepository:
    def __init__(self) -> None:
        self._sessions: dict[str, UploadSessionData] = {}
        self._lock = threading.RLock()

    def create(self, session: UploadSessionData) -> UploadSessionData:
        with self._lock:
            if session.id in self._sessions:
                raise ConflictError("upload session exists", details={"id": session.id})
            self._sessions[session.id] = session
            return session

    def get(self, session_id: str) -> UploadSessionData:
        with self._lock:
            try:
                return self._sessions[session_id]
            except KeyError:
                raise NotFoundError("upload session not found", details={"id": session_id}) from None

    def update(self, session: UploadSessionData) -> UploadSessionData:
        with self._lock:
            if session.id not in self._sessions:
                raise NotFoundError("upload session not found", details={"id": session.id}) from None
            self._sessions[session.id] = session
            return session

    def compare_and_set_status(self, session_id: str, expect: str, new: str) -> bool:
        with self._lock:
            current = self._sessions.get(session_id)
            if current is None:
                raise NotFoundError("upload session not found", details={"id": session_id}) from None
            if current.status != expect:
                return False
            current.status = new
            current.updated_at = utcnow()
            self._sessions[session_id] = current
            return True

    def delete(self, session_id: str) -> None:
        with self._lock:
            if session_id not in self._sessions:
                raise NotFoundError("upload session not found", details={"id": session_id}) from None
            del self._sessions[session_id]

    def list_expired(self, before, limit: int = 100) -> list[UploadSessionData]:
        moment = ensure_utc(before)
        with self._lock:
            items = [
                s for s in self._sessions.values() if ensure_utc(s.expires_at) <= moment and s.status == "active"
            ]
            items.sort(key=lambda s: (ensure_utc(s.expires_at), s.id))
            return items[:limit]
