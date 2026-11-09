"""SQLAlchemy repository backends.

Persistent implementations of the repository protocols on top of a session
factory. Every operation runs through :func:`rescs.db.session.session_scope`,
which provides transaction handling and converts raw database failures into
domain errors.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, and_, cast, func, or_

from rescs.db.session import SessionFactory, session_scope
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
from rescs.models import AuditEvent, FileObject, Record
from rescs.models.upload_session import UploadSession


def _tag_pattern(column, tag: str):
    """Exact-element LIKE match on a JSON tag array.

    Tags cannot contain quotes/backslashes (validated charset), so matching
    the double-quoted element is exact. ``_``/``%``/``\\`` are escaped because
    ``_`` is a legal tag character and a LIKE wildcard.
    """
    escaped = _like_escape(tag)
    return cast(column, String).like(f'%"{escaped}"%', escape="\\")


def _like_escape(raw: str) -> str:
    """Escape LIKE wildcards in free-text user input."""
    return (
        raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )


def _live_record_filter(now: datetime):
    return and_(
        Record.deleted_at.is_(None),
        or_(Record.expires_at.is_(None), Record.expires_at > now),
    )


def _live_file_filter(now: datetime):
    return and_(
        FileObject.deleted_at.is_(None),
        or_(FileObject.expires_at.is_(None), FileObject.expires_at > now),
    )


def _apply_window(query, column, after, before):
    if after is not None:
        query = query.filter(column >= ensure_utc(after))
    if before is not None:
        query = query.filter(column < ensure_utc(before))
    return query


class SQLAlchemyRecordRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def create(self, record: RecordData) -> RecordData:
        with session_scope(
            self._session_factory,
            "create record",
            conflict=lambda: self._conflict(record),
        ) as session:
            if session.get(Record, record.id) is not None:
                raise ConflictError("record already exists", details={"id": record.id})
            session.add(Record.from_domain(record))
        return record

    def get(self, record_id: str) -> RecordData:
        now = utcnow()
        with session_scope(self._session_factory, "get record") as session:
            row = session.get(Record, record_id)
            if row is None:
                raise NotFoundError("record not found", details={"id": record_id})
            data = row.to_domain()
            if data.deleted_at is not None or data.is_expired(now):
                raise NotFoundError("record not found", details={"id": record_id})
            return data

    def get_including_deleted(self, record_id: str) -> RecordData:
        with session_scope(self._session_factory, "get record") as session:
            row = session.get(Record, record_id)
            if row is None:
                raise NotFoundError("record not found", details={"id": record_id})
            return row.to_domain()

    def find_occupant(self, namespace: str, key: str) -> RecordData | None:
        with session_scope(self._session_factory, "find record occupant") as session:
            row = (
                session.query(Record)
                .filter(Record.namespace == namespace, Record.key == key)
                .first()
            )
            return row.to_domain() if row is not None else None

    def get_by_namespace_key(self, namespace: str, key: str) -> RecordData | None:
        now = utcnow()
        with session_scope(self._session_factory, "get record by namespace/key") as session:
            row = (
                session.query(Record)
                .filter(
                    Record.namespace == namespace,
                    Record.key == key,
                    _live_record_filter(now),
                )
                .first()
            )
            return row.to_domain() if row is not None else None

    def update(self, record: RecordData) -> RecordData:
        with session_scope(
            self._session_factory,
            "update record",
            conflict=lambda: self._conflict(record),
        ) as session:
            row = session.get(Record, record.id)
            if row is None:
                raise NotFoundError("record not found", details={"id": record.id})
            row.namespace = record.namespace
            row.key = record.key
            row.value = record.value
            row.meta = record.metadata
            row.owner = record.owner
            row.version = record.version
            row.idempotency_key = record.idempotency_key
            row.etag = record.etag
            row.updated_at = record.updated_at
            row.tags = list(record.tags or [])
            row.expires_at = ensure_utc(record.expires_at)
            row.deleted_at = ensure_utc(record.deleted_at)
            row.deleted_by = record.deleted_by
        return record

    def delete(self, record_id: str) -> None:
        with session_scope(self._session_factory, "delete record") as session:
            row = session.get(Record, record_id)
            if row is None:
                raise NotFoundError("record not found", details={"id": record_id})
            session.delete(row)

    def find_by_idempotency_key(self, idempotency_key: str) -> RecordData | None:
        with session_scope(self._session_factory, "find record by idempotency key") as session:
            row = (
                session.query(Record)
                .filter(Record.idempotency_key == idempotency_key)
                .first()
            )
            return row.to_domain() if row is not None else None

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
    ) -> Page[RecordData]:
        now = utcnow()
        with session_scope(self._session_factory, "list records") as session:
            query = session.query(Record)
            if namespace is not None:
                query = query.filter(Record.namespace == namespace)
            if key_prefix is not None:
                query = query.filter(
                    Record.key.like(f"{_like_escape(key_prefix)}%", escape="\\")
                )
            if owner is not None:
                query = query.filter(Record.owner == owner)
            for tag in tags or []:
                query = query.filter(_tag_pattern(Record.tags, tag))
            query = _apply_window(query, Record.created_at, created_after, created_before)
            query = _apply_window(query, Record.updated_at, updated_after, updated_before)
            if not include_deleted:
                query = query.filter(Record.deleted_at.is_(None))
            if not include_expired:
                query = query.filter(
                    or_(Record.expires_at.is_(None), Record.expires_at > now)
                )
            total = query.count()
            rows = (
                query.order_by(Record.updated_at.asc(), Record.id.asc())
                .limit(limit)
                .offset(offset)
                .all()
            )
            items = [row.to_domain() for row in rows]
            return Page(items=items, total=total, limit=limit, offset=offset)

    def list_deleted(
        self,
        namespace: str | None = None,
        owner: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Page[RecordData]:
        with session_scope(self._session_factory, "list deleted records") as session:
            query = session.query(Record).filter(Record.deleted_at.is_not(None))
            if namespace is not None:
                query = query.filter(Record.namespace == namespace)
            if owner is not None:
                query = query.filter(Record.owner == owner)
            total = query.count()
            rows = (
                query.order_by(Record.deleted_at.desc(), Record.id.asc())
                .limit(limit)
                .offset(offset)
                .all()
            )
            items = [row.to_domain() for row in rows]
            return Page(items=items, total=total, limit=limit, offset=offset)

    def list_expired(self, before: datetime, limit: int = 100) -> list[RecordData]:
        with session_scope(self._session_factory, "list expired records") as session:
            rows = (
                session.query(Record)
                .filter(
                    Record.expires_at.is_not(None),
                    Record.expires_at <= ensure_utc(before),
                )
                .order_by(Record.expires_at.asc(), Record.id.asc())
                .limit(limit)
                .all()
            )
            return [row.to_domain() for row in rows]

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
        pattern = f"%{_like_escape(query)}%"
        now = utcnow()
        with session_scope(self._session_factory, "search records") as session:
            base = session.query(Record)
            if namespace is not None:
                base = base.filter(Record.namespace == namespace)
            if owner is not None:
                base = base.filter(Record.owner == owner)
            for tag in tags or []:
                base = base.filter(_tag_pattern(Record.tags, tag))
            if not include_deleted:
                base = base.filter(Record.deleted_at.is_(None))
            if not include_expired:
                base = base.filter(
                    or_(Record.expires_at.is_(None), Record.expires_at > now)
                )
            condition = or_(
                Record.key.ilike(pattern, escape="\\"),
                cast(Record.meta, String).ilike(pattern, escape="\\"),
                cast(Record.value, String).ilike(pattern, escape="\\"),
            )
            matching = base.filter(condition)
            total = matching.count()
            rows = (
                matching.order_by(Record.updated_at.asc(), Record.id.asc())
                .limit(limit)
                .offset(offset)
                .all()
            )
            items = [row.to_domain() for row in rows]
            return Page(items=items, total=total, limit=limit, offset=offset)

    def count_by_owner(self, owner: str, *, include_deleted: bool = False) -> int:
        now = utcnow()
        with session_scope(self._session_factory, "count records by owner") as session:
            query = session.query(func.count(Record.id)).filter(Record.owner == owner)
            if not include_deleted:
                query = query.filter(Record.deleted_at.is_(None))
            query = query.filter(
                or_(Record.expires_at.is_(None), Record.expires_at > now)
            )
            return int(query.scalar() or 0)

    @staticmethod
    def _conflict(record: RecordData) -> ConflictError:
        return ConflictError(
            "a record with the same id, namespace/key, or idempotency key "
            "already exists",
            details={
                "id": record.id,
                "namespace": record.namespace,
                "key": record.key,
                "idempotency_key": record.idempotency_key,
            },
        )


class SQLAlchemyFileObjectRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def create(self, file_object: FileObjectData) -> FileObjectData:
        with session_scope(
            self._session_factory,
            "create file object",
            conflict=lambda: self._conflict(file_object),
        ) as session:
            if session.get(FileObject, file_object.id) is not None:
                raise ConflictError(
                    "file object already exists", details={"id": file_object.id}
                )
            session.add(FileObject.from_domain(file_object))
        return file_object

    def get(self, file_id: str) -> FileObjectData:
        now = utcnow()
        with session_scope(self._session_factory, "get file object") as session:
            row = session.get(FileObject, file_id)
            if row is None:
                raise NotFoundError("file not found", details={"id": file_id})
            data = row.to_domain()
            if data.deleted_at is not None or data.is_expired(now):
                raise NotFoundError("file not found", details={"id": file_id})
            return data

    def get_including_deleted(self, file_id: str) -> FileObjectData:
        with session_scope(self._session_factory, "get file object") as session:
            row = session.get(FileObject, file_id)
            if row is None:
                raise NotFoundError("file not found", details={"id": file_id})
            return row.to_domain()

    def update(self, file_object: FileObjectData) -> FileObjectData:
        with session_scope(
            self._session_factory,
            "update file object",
            conflict=lambda: self._conflict(file_object),
        ) as session:
            row = session.get(FileObject, file_object.id)
            if row is None:
                raise NotFoundError("file not found", details={"id": file_object.id})
            row.filename = file_object.filename
            row.mime_type = file_object.mime_type
            row.size = file_object.size
            row.storage_path = file_object.storage_path
            row.sha256 = file_object.sha256
            row.meta = file_object.metadata
            row.owner = file_object.owner
            row.version = file_object.version
            row.idempotency_key = file_object.idempotency_key
            row.etag = file_object.etag
            row.updated_at = file_object.updated_at
            row.tags = list(file_object.tags or [])
            row.expires_at = ensure_utc(file_object.expires_at)
            row.deleted_at = ensure_utc(file_object.deleted_at)
            row.deleted_by = file_object.deleted_by
        return file_object

    def delete(self, file_id: str) -> None:
        with session_scope(self._session_factory, "delete file object") as session:
            row = session.get(FileObject, file_id)
            if row is None:
                raise NotFoundError("file not found", details={"id": file_id})
            session.delete(row)

    def find_by_idempotency_key(self, idempotency_key: str) -> FileObjectData | None:
        with session_scope(self._session_factory, "find file by idempotency key") as session:
            row = (
                session.query(FileObject)
                .filter(FileObject.idempotency_key == idempotency_key)
                .first()
            )
            return row.to_domain() if row is not None else None

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
    ) -> Page[FileObjectData]:
        now = utcnow()
        with session_scope(self._session_factory, "list file objects") as session:
            query = session.query(FileObject)
            if owner is not None:
                query = query.filter(FileObject.owner == owner)
            for tag in tags or []:
                query = query.filter(_tag_pattern(FileObject.tags, tag))
            if mime_type is not None:
                query = query.filter(FileObject.mime_type == mime_type)
            if size_min is not None:
                query = query.filter(FileObject.size >= size_min)
            if size_max is not None:
                query = query.filter(FileObject.size <= size_max)
            query = _apply_window(query, FileObject.created_at, created_after, created_before)
            query = _apply_window(query, FileObject.updated_at, updated_after, updated_before)
            if not include_deleted:
                query = query.filter(FileObject.deleted_at.is_(None))
            if not include_expired:
                query = query.filter(
                    or_(FileObject.expires_at.is_(None), FileObject.expires_at > now)
                )
            total = query.count()
            rows = (
                query.order_by(FileObject.updated_at.asc(), FileObject.id.asc())
                .limit(limit)
                .offset(offset)
                .all()
            )
            items = [row.to_domain() for row in rows]
            return Page(items=items, total=total, limit=limit, offset=offset)

    def list_deleted(
        self,
        owner: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Page[FileObjectData]:
        with session_scope(self._session_factory, "list deleted files") as session:
            query = session.query(FileObject).filter(FileObject.deleted_at.is_not(None))
            if owner is not None:
                query = query.filter(FileObject.owner == owner)
            total = query.count()
            rows = (
                query.order_by(FileObject.deleted_at.desc(), FileObject.id.asc())
                .limit(limit)
                .offset(offset)
                .all()
            )
            items = [row.to_domain() for row in rows]
            return Page(items=items, total=total, limit=limit, offset=offset)

    def list_expired(self, before: datetime, limit: int = 100) -> list[FileObjectData]:
        with session_scope(self._session_factory, "list expired files") as session:
            rows = (
                session.query(FileObject)
                .filter(
                    FileObject.expires_at.is_not(None),
                    FileObject.expires_at <= ensure_utc(before),
                )
                .order_by(FileObject.expires_at.asc(), FileObject.id.asc())
                .limit(limit)
                .all()
            )
            return [row.to_domain() for row in rows]

    def count_by_owner(self, owner: str, *, include_deleted: bool = False) -> int:
        now = utcnow()
        with session_scope(self._session_factory, "count files by owner") as session:
            query = session.query(func.count(FileObject.id)).filter(
                FileObject.owner == owner
            )
            if not include_deleted:
                query = query.filter(FileObject.deleted_at.is_(None))
            query = query.filter(
                or_(FileObject.expires_at.is_(None), FileObject.expires_at > now)
            )
            return int(query.scalar() or 0)

    def bytes_by_owner(self, owner: str, *, include_deleted: bool = False) -> int:
        now = utcnow()
        with session_scope(self._session_factory, "sum file bytes by owner") as session:
            query = session.query(func.coalesce(func.sum(FileObject.size), 0)).filter(
                FileObject.owner == owner
            )
            if not include_deleted:
                query = query.filter(FileObject.deleted_at.is_(None))
            query = query.filter(
                or_(FileObject.expires_at.is_(None), FileObject.expires_at > now)
            )
            return int(query.scalar() or 0)

    @staticmethod
    def _conflict(file_object: FileObjectData) -> ConflictError:
        return ConflictError(
            "a file with the same id or idempotency key already exists",
            details={"id": file_object.id, "idempotency_key": file_object.idempotency_key},
        )


class SQLAlchemyAuditRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def append(self, event: AuditData) -> AuditData:
        with session_scope(self._session_factory, "append audit event") as session:
            if session.get(AuditEvent, event.id) is not None:
                raise ConflictError(
                    "audit event already exists", details={"id": event.id}
                )
            session.add(AuditEvent.from_domain(event))
        return event

    def list(
        self,
        owner: str | None = None,
        operation: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Page[AuditData]:
        with session_scope(self._session_factory, "list audit events") as session:
            query = session.query(AuditEvent)
            if owner is not None:
                query = query.filter(AuditEvent.owner == owner)
            if operation is not None:
                query = query.filter(AuditEvent.operation == operation)
            if since is not None:
                query = query.filter(AuditEvent.timestamp >= ensure_utc(since))
            total = query.count()
            rows = (
                query.order_by(AuditEvent.timestamp.asc(), AuditEvent.id.asc())
                .limit(limit)
                .offset(offset)
                .all()
            )
            items = [row.to_domain() for row in rows]
            return Page(items=items, total=total, limit=limit, offset=offset)

    def prune_before(self, cutoff: datetime) -> int:
        with session_scope(self._session_factory, "prune audit events") as session:
            deleted = (
                session.query(AuditEvent)
                .filter(AuditEvent.timestamp < ensure_utc(cutoff))
                .delete(synchronize_session=False)
            )
            return int(deleted or 0)


class SQLAlchemyUploadSessionRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def create(self, session_data: UploadSessionData) -> UploadSessionData:
        with session_scope(self._session_factory, "create upload session") as session:
            if session.get(UploadSession, session_data.id) is not None:
                raise ConflictError("upload session exists", details={"id": session_data.id})
            session.add(UploadSession.from_domain(session_data))
        return session_data

    def get(self, session_id: str) -> UploadSessionData:
        with session_scope(self._session_factory, "get upload session") as session:
            row = session.get(UploadSession, session_id)
            if row is None:
                raise NotFoundError("upload session not found", details={"id": session_id})
            return row.to_domain()

    def update(self, session_data: UploadSessionData) -> UploadSessionData:
        with session_scope(self._session_factory, "update upload session") as session:
            row = session.get(UploadSession, session_data.id)
            if row is None:
                raise NotFoundError("upload session not found", details={"id": session_data.id})
            updated = UploadSession.from_domain(session_data)
            session.merge(updated)
        return session_data

    def compare_and_set_status(self, session_id: str, expect: str, new: str) -> bool:
        with session_scope(self._session_factory, "cas upload session") as session:
            matched = (
                session.query(UploadSession)
                .filter(UploadSession.id == session_id)
                .filter(UploadSession.status == expect)
                .update(
                    {UploadSession.status: new, UploadSession.updated_at: utcnow()},
                    synchronize_session=False,
                )
            )
            if matched == 1:
                return True
            if session.get(UploadSession, session_id) is None:
                raise NotFoundError("upload session not found", details={"id": session_id})
            return False

    def delete(self, session_id: str) -> None:
        with session_scope(self._session_factory, "delete upload session") as session:
            row = session.get(UploadSession, session_id)
            if row is None:
                raise NotFoundError("upload session not found", details={"id": session_id})
            session.delete(row)

    def list_expired(self, before: datetime, limit: int = 100) -> list[UploadSessionData]:
        with session_scope(self._session_factory, "list expired uploads") as session:
            rows = (
                session.query(UploadSession)
                .filter(UploadSession.expires_at <= ensure_utc(before))
                .filter(UploadSession.status == "active")
                .order_by(UploadSession.expires_at.asc(), UploadSession.id.asc())
                .limit(limit)
                .all()
            )
            return [row.to_domain() for row in rows]
