"""Service composition root.

Constructs the application service layer from a database (persistent) or
from in-memory backends (tests/demo), plus an object store for binary files.
The API layer consumes this ready-made set of services and never assembles
repositories or stores itself.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from rescs.config import Settings
from rescs.db.bootstrap import Database
from rescs.interfaces.object_store import ObjectStore
from rescs.repositories.memory import (
    InMemoryAuditRepository,
    InMemoryFileObjectRepository,
    InMemoryRecordRepository,
    InMemoryUploadSessionRepository,
)
from rescs.repositories.sqlalchemy_ import (
    SQLAlchemyAuditRepository,
    SQLAlchemyFileObjectRepository,
    SQLAlchemyRecordRepository,
    SQLAlchemyUploadSessionRepository,
)
from rescs.services.audit import AuditService
from rescs.services.files import FileService
from rescs.services.records import RecordService
from rescs.services.uploads import UploadService
from rescs.storage.local import LocalObjectStore
from rescs.storage.memory import MemoryObjectStore

DEFAULT_STORAGE_DIR = "rescs_storage"


@dataclass
class Services:
    records: RecordService
    files: FileService
    audit: AuditService
    uploads: UploadService


def _default_object_store(use_memory: bool, storage_dir: str | None) -> ObjectStore:
    if use_memory:
        return MemoryObjectStore()
    return LocalObjectStore(storage_dir or DEFAULT_STORAGE_DIR)


def build_services(
    *,
    database: Database | None = None,
    use_memory: bool = False,
    object_store: ObjectStore | None = None,
    storage_dir: str | os.PathLike[str] | None = None,
    settings: Settings | None = None,
) -> Services:
    """Build the service layer.

    :param database: persistent backend (engine + session factory).
    :param use_memory: when true (or when ``database`` is None) use the
        in-memory repositories.
    :param object_store: explicit object store; defaults from settings
        (local/memory/s3) or directory fallback.
    :param storage_dir: base directory for the default local object store.
    :param settings: runtime settings for quotas/governance (optional).
    """
    if object_store is None and settings is not None:
        backend = (getattr(settings, "storage_backend", "local") or "local").lower()
        if backend == "memory":
            object_store = MemoryObjectStore()
        elif backend == "s3":
            from rescs.storage.s3 import build_object_store

            object_store = build_object_store(settings)  # type: ignore[assignment]
        elif storage_dir is not None or getattr(settings, "storage_dir", None):
            object_store = LocalObjectStore(str(storage_dir or settings.storage_dir))
    if database is None or use_memory:
        shared_audit = AuditService(InMemoryAuditRepository())
        records = RecordService(
            InMemoryRecordRepository(), settings=settings, audit=shared_audit
        )
        store = object_store or MemoryObjectStore()
        files_repo = InMemoryFileObjectRepository()
        files = FileService(
            files_repo,
            store,
            settings=settings,
            audit=shared_audit,
        )
        uploads = UploadService(
            InMemoryUploadSessionRepository(),
            files_repo,
            store,
            settings=settings,
            audit=shared_audit,
        )
        audit = shared_audit
    else:
        if object_store is None:
            object_store = LocalObjectStore(
                str(storage_dir or DEFAULT_STORAGE_DIR)
            )
        audit_service = AuditService(SQLAlchemyAuditRepository(database.session_factory))
        records = RecordService(
            SQLAlchemyRecordRepository(database.session_factory),
            settings=settings,
            audit=audit_service,
        )
        files_repo = SQLAlchemyFileObjectRepository(database.session_factory)
        files = FileService(
            files_repo,
            object_store,
            settings=settings,
            audit=audit_service,
        )
        uploads = UploadService(
            SQLAlchemyUploadSessionRepository(database.session_factory),
            files_repo,
            object_store,
            settings=settings,
            audit=audit_service,
        )
        audit = audit_service
    return Services(records=records, files=files, audit=audit, uploads=uploads)
