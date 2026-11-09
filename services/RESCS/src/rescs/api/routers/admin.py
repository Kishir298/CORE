"""Administrative endpoints: expiry cleanup, audit trail, recovery lists.

All routes require a valid ``X-API-Key`` and honor the same owner-scoping
rules as the rest of the API: in single-owner lock mode every response is
confined to the locked owner.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from rescs.api.deps import get_services, get_settings
from rescs.config import Settings
from rescs.domain import utcnow
from rescs.schemas.audit import AuditPage, AuditRead
from rescs.schemas.file_object import FileObjectPage, FileObjectRead
from rescs.schemas.record import RecordPage, RecordRead
from rescs.security import require_api_key, scoped_query_owner
from rescs.services.factory import Services

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_api_key)],
)


class CleanupRequest(BaseModel):
    dry_run: bool = False
    batch: int = Field(default=500, ge=1, le=5000)


class CleanupResponse(BaseModel):
    dry_run: bool
    records_purged: int
    files_purged: int
    audit_pruned: int
    uploads_cleaned: int = 0


@router.post("/cleanup", response_model=CleanupResponse)
def run_cleanup(
    payload: CleanupRequest,
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
) -> CleanupResponse:
    now = utcnow()
    if payload.dry_run:
        return CleanupResponse(
            dry_run=True,
            records_purged=services.records.count_expired(limit=payload.batch),
            files_purged=services.files.count_expired(limit=payload.batch),
            audit_pruned=0,
            uploads_cleaned=len(services.uploads._sessions.list_expired(now, limit=payload.batch)),
        )
    records_purged = services.records.cleanup_expired(actor=principal, limit=payload.batch)
    files_purged = services.files.cleanup_expired(actor=principal, limit=payload.batch)
    uploads_cleaned = services.uploads.cleanup_expired(actor=principal, limit=payload.batch)
    audit_pruned = 0
    if settings.audit_retention_days:
        cutoff = now - timedelta(days=settings.audit_retention_days)
        audit_pruned = services.audit.prune_before(cutoff)
    return CleanupResponse(
        dry_run=False,
        records_purged=records_purged,
        files_purged=files_purged,
        audit_pruned=audit_pruned,
        uploads_cleaned=uploads_cleaned,
    )


@router.get("/audit", response_model=AuditPage)
def list_audit(
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    owner: str | None = Query(default=None),
    operation: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AuditPage:
    owner = scoped_query_owner(owner=owner, principal=principal, settings=settings)
    page = services.audit.list(
        owner=owner, operation=operation, since=since, limit=limit, offset=offset
    )
    return AuditPage(
        items=[AuditRead.from_domain(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/records/deleted", response_model=RecordPage)
def list_deleted_records(
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    namespace: str | None = Query(default=None),
    owner: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> RecordPage:
    owner = scoped_query_owner(owner=owner, principal=principal, settings=settings)
    page = services.records.list_deleted(
        namespace=namespace, owner=owner, limit=limit, offset=offset
    )
    return RecordPage(
        items=[RecordRead.from_domain(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/files/deleted", response_model=FileObjectPage)
def list_deleted_files(
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    owner: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> FileObjectPage:
    owner = scoped_query_owner(owner=owner, principal=principal, settings=settings)
    page = services.files.list_deleted(owner=owner, limit=limit, offset=offset)
    return FileObjectPage(
        items=[FileObjectRead.from_domain(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )

