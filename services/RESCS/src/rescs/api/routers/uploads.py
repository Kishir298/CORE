"""Resumable upload API: sessions, chunks, finalize, cancel."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request

from rescs.api.deps import get_services, get_settings
from rescs.config import Settings
from rescs.schemas.file_object import FileObjectRead
from rescs.schemas.upload import UploadCreate, UploadRead
from rescs.security import (
    assert_device_ownership,
    assert_principal_is_owner,
    enforce_owner,
    get_device_id,
    require_api_key,
    validate_device_owner,
)
from rescs.services.factory import Services

router = APIRouter(
    prefix="/uploads",
    tags=["uploads"],
    dependencies=[Depends(require_api_key)],
)


def _apply_device_scope(
    *,
    owner: str | None,
    device_id: str | None,
    operation: str,
) -> str | None:
    """Apply device-scoped validation/transformation to owner."""
    if device_id is None:
        return owner
    if owner is not None:
        owner = validate_device_owner(owner, device_id, operation)
    return owner


@router.post("", status_code=201, response_model=UploadRead)
def create_upload(
    payload: UploadCreate,
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    device_id: str | None = Depends(get_device_id),
) -> UploadRead:
    owner = enforce_owner(requested=payload.owner, principal=principal, settings=settings)
    owner = _apply_device_scope(owner=owner, device_id=device_id, operation="create upload")
    session = services.uploads.create(
        owner=owner,
        filename=payload.filename,
        content_type=payload.content_type,
        total_size=payload.total_size,
        chunk_size=payload.chunk_size,
        checksum=payload.checksum,
        metadata=payload.metadata,
        tags=payload.tags,
        actor=principal,
    )
    return UploadRead.from_domain(session)


@router.get("/{session_id}", response_model=UploadRead)
def get_upload(
    session_id: str,
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    device_id: str | None = Depends(get_device_id),
) -> UploadRead:
    session = services.uploads.get(session_id)
    assert_principal_is_owner(record_owner=session.owner, principal=principal, settings=settings)
    if device_id is not None:
        assert_device_ownership(
            resource_owner=session.owner,
            resource_namespace="uploads",
            device_id=device_id,
            operation="read upload",
        )
    return UploadRead.from_domain(session)


@router.put("/{session_id}/chunks", response_model=UploadRead)
async def put_chunk(
    session_id: str,
    request: Request,
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    device_id: str | None = Depends(get_device_id),
    content_range: str | None = Header(default=None, alias="Content-Range"),
    offset: int | None = None,
) -> UploadRead:
    # Owner check before reading body.
    session = services.uploads.get(session_id)
    assert_principal_is_owner(record_owner=session.owner, principal=principal, settings=settings)
    if device_id is not None:
        assert_device_ownership(
            resource_owner=session.owner,
            resource_namespace="uploads",
            device_id=device_id,
            operation="upload chunk",
        )
    if offset is None and content_range:
        # Accept "bytes <offset>-<end>/<total>" — use start offset.
        try:
            units, _, rng = content_range.partition(" ")
            start_end, _, _total = (rng or content_range).partition("/")
            start, _, _end = start_end.partition("-")
            offset = int(start.strip())
        except ValueError:
            offset = None
    query_offset = request.query_params.get("offset")
    if offset is None and query_offset is not None:
        try:
            offset = int(query_offset)
        except ValueError:
            offset = None
    if offset is None:
        from rescs.errors import InvalidRequestError

        raise InvalidRequestError("chunk offset required (?offset= or Content-Range)", details={})
    # Bounded intake: fail fast on Content-Length, then stream with a cap
    # so a huge body cannot OOM via unbounded request.body().
    from rescs.errors import PayloadTooLargeError

    allowed = session.chunk_size
    if settings.max_file_size and settings.max_file_size > 0:
        allowed = min(allowed, settings.max_file_size)
    claimed = request.headers.get("content-length")
    if claimed is not None:
        try:
            if int(claimed) > allowed:
                raise PayloadTooLargeError(
                    f"chunk exceeds maximum of {allowed} bytes",
                    details={"size": int(claimed), "max": allowed},
                )
        except ValueError:
            pass
    parts: list[bytes] = []
    received = 0
    async for piece in request.stream():
        if not piece:
            continue
        received += len(piece)
        if received > allowed:
            raise PayloadTooLargeError(
                f"chunk exceeds maximum of {allowed} bytes",
                details={"size": received, "max": allowed},
            )
        parts.append(piece)
    data = b"".join(parts)
    updated = services.uploads.put_chunk(session_id, offset, data, actor=principal)
    return UploadRead.from_domain(updated)


@router.post("/{session_id}/finalize", response_model=FileObjectRead)
def finalize_upload(
    session_id: str,
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    device_id: str | None = Depends(get_device_id),
) -> FileObjectRead:
    session = services.uploads.get(session_id)
    assert_principal_is_owner(record_owner=session.owner, principal=principal, settings=settings)
    if device_id is not None:
        assert_device_ownership(
            resource_owner=session.owner,
            resource_namespace="uploads",
            device_id=device_id,
            operation="finalize upload",
        )
    file_obj = services.uploads.finalize(session_id, actor=principal)
    return FileObjectRead.from_domain(file_obj)


@router.delete("/{session_id}", status_code=204)
def cancel_upload(
    session_id: str,
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    device_id: str | None = Depends(get_device_id),
) -> None:
    session = services.uploads.get(session_id)
    assert_principal_is_owner(record_owner=session.owner, principal=principal, settings=settings)
    if device_id is not None:
        assert_device_ownership(
            resource_owner=session.owner,
            resource_namespace="uploads",
            device_id=device_id,
            operation="cancel upload",
        )
    services.uploads.cancel(session_id, actor=principal)

