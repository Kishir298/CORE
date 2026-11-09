"""File storage API endpoints.

Bytes are transported as multipart uploads / binary downloads; metadata is
JSON. Files are addressed by their stable id. All routes require a valid
``X-API-Key``.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Header, Query, Response, UploadFile
from fastapi.responses import StreamingResponse

from rescs.api.deps import get_services, get_settings, parse_etag
from rescs.config import Settings
from rescs.domain import normalize_tags
from rescs.errors import InvalidRequestError, PayloadTooLargeError
from rescs.schemas.file_object import FileObjectCreate, FileObjectPage, FileObjectRead
from rescs.security import (
    assert_device_ownership,
    assert_principal_is_owner,
    enforce_owner,
    get_device_id,
    require_api_key,
    scoped_query_owner,
    validate_device_owner,
)
from rescs.services.factory import Services

router = APIRouter(
    prefix="/files",
    tags=["files"],
    dependencies=[Depends(require_api_key)],
)


@router.post("", status_code=201, response_model=FileObjectRead)
async def upload_file(
    upload: UploadFile = File(...),
    owner: str = Form(default="system"),
    tags: list[str] = Form(default=[]),
    expires_at: str | None = Form(default=None),
    ttl_seconds: int | None = Form(default=None),
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    device_id: str | None = Depends(get_device_id),
) -> FileObjectRead:
    import tempfile

    from rescs.interfaces.object_store import CHUNK_SIZE

    threshold = settings.streaming_threshold_bytes or 8 * 1024 * 1024
    # Bounded-memory spool: small payloads stay in RAM, large spill to disk.
    # Never holds more than ~1MiB in RAM at once during intake.
    spool = tempfile.SpooledTemporaryFile(max_size=threshold)
    # Total-intake bound: reject oversized uploads during spooling so a
    # huge body cannot fill spool disk before governance sees it.
    max_intake = settings.max_file_size or 0
    received = 0
    try:
        while True:
            chunk = await upload.read(CHUNK_SIZE)
            if not chunk:
                break
            received += len(chunk)
            if max_intake and received > max_intake:
                raise PayloadTooLargeError(
                    f"file exceeds maximum size of {max_intake} bytes",
                    details={"size": received, "max": max_intake},
                )
            spool.write(chunk)
        spool.seek(0)

        def _chunks():
            while True:
                piece = spool.read(CHUNK_SIZE)
                if not piece:
                    break
                yield piece

        payload = FileObjectCreate(filename=upload.filename or "unnamed")
        payload.owner = enforce_owner(
            requested=owner, principal=principal, settings=settings
        )
        payload.owner = _apply_device_scope(
            owner=payload.owner,
            device_id=device_id,
            operation="upload file",
        )
        payload.tags = normalize_tags(tags)
        if expires_at is not None:
            try:
                payload.expires_at = datetime.fromisoformat(expires_at)
            except ValueError:
                raise InvalidRequestError(
                    "expires_at must be ISO-8601",
                    details={"expires_at": expires_at},
                ) from None
        if ttl_seconds is not None:
            payload.ttl_seconds = ttl_seconds
        mime_type = _sniff_mime(upload.content_type)
        if mime_type != "application/octet-stream":
            payload.mime_type = mime_type
        return FileObjectRead.from_domain(
            services.files.create_stream(payload, _chunks())
        )
    finally:
        try:
            spool.close()
        except Exception:
            pass


def _sniff_mime(content_type: str | None) -> str:
    if not content_type:
        return "application/octet-stream"
    return content_type.split(";")[0].strip()


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


def _content_disposition(filename: str | None) -> str:
    """Build a header-safe attachment disposition for an untrusted filename.

    Strips CR/LF + quotes/backslashes (header injection), falls back to
    ``download`` when nothing safe remains, and appends an RFC 5987
    ``filename*`` UTF-8 part so non-ASCII names survive intact.
    """
    from urllib.parse import quote

    raw = (filename or "").strip() or "download"
    safe = "".join(
        ch for ch in raw if ch not in '\r\n"\\' and ord(ch) >= 0x20
    ).strip()
    if not safe:
        safe = "download"
    if len(safe) > 180:
        safe = safe[:180]
    try:
        encoded = quote(raw, safe="")
    except Exception:
        encoded = quote(safe, safe="")
    if encoded == safe:
        return f'attachment; filename="{safe}"'
    return f'attachment; filename="{safe}"; filename*=UTF-8\'\'{encoded}'


@router.get("", response_model=FileObjectPage)
def list_files(
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    device_id: str | None = Depends(get_device_id),
    owner: str | None = Query(default=None),
    tags: list[str] | None = Query(default=None),
    mime_type: str | None = Query(default=None),
    size_min: int | None = Query(default=None, ge=0),
    size_max: int | None = Query(default=None, ge=0),
    created_after: datetime | None = Query(default=None),
    created_before: datetime | None = Query(default=None),
    updated_after: datetime | None = Query(default=None),
    updated_before: datetime | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    include_expired: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> FileObjectPage:
    owner = scoped_query_owner(owner=owner, principal=principal, settings=settings)
    owner = _apply_device_scope(
        owner=owner,
        device_id=device_id,
        operation="list files",
    )
    page = services.files.list(
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
    return FileObjectPage(
        items=[FileObjectRead.from_domain(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


def _authorized_file(
    services: Services,
    file_id: str,
    *,
    principal: str,
    settings: Settings,
    device_id: str | None = None,
) -> object:
    meta = services.files.get(file_id)
    assert_principal_is_owner(
        record_owner=meta.owner, principal=principal, settings=settings
    )
    if device_id is not None:
        assert_device_ownership(
            resource_owner=meta.owner,
            resource_namespace=meta.namespace if hasattr(meta, "namespace") else "files",
            device_id=device_id,
            operation="read file",
        )
    return meta


def _authorized_file_including_deleted(
    services: Services,
    file_id: str,
    *,
    principal: str,
    settings: Settings,
    device_id: str | None = None,
) -> object:
    meta = services.files.get_including_deleted(file_id)
    assert_principal_is_owner(
        record_owner=meta.owner, principal=principal, settings=settings
    )
    if device_id is not None:
        assert_device_ownership(
            resource_owner=meta.owner,
            resource_namespace=meta.namespace if hasattr(meta, "namespace") else "files",
            device_id=device_id,
            operation="read file",
        )
    return meta


@router.get("/{file_id}", response_model=FileObjectRead)
def get_file_metadata(
    file_id: str,
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    device_id: str | None = Depends(get_device_id),
) -> FileObjectRead:
    return FileObjectRead.from_domain(
        _authorized_file(services, file_id, principal=principal, settings=settings, device_id=device_id)
    )


@router.get("/{file_id}/content")
def download_file(
    file_id: str,
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    device_id: str | None = Depends(get_device_id),
) -> Response:
    meta = _authorized_file(
        services, file_id, principal=principal, settings=settings, device_id=device_id
    )
    threshold = settings.streaming_threshold_bytes or 8 * 1024 * 1024
    headers = {
        "Content-Disposition": _content_disposition(meta.filename),
        "X-File-SHA256": meta.sha256,
        "X-File-Size": str(meta.size),
        "ETag": f'"{meta.etag}"',
    }
    if meta.size >= threshold:
        _meta, stream = services.files.download_stream(file_id)
        return StreamingResponse(
            stream, media_type=meta.mime_type, headers=headers
        )
    _meta, data = services.files.download(file_id)
    return Response(
        content=data,
        media_type=meta.mime_type,
        headers=headers,
    )


@router.delete("/{file_id}", status_code=204)
def delete_file(
    file_id: str,
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    device_id: str | None = Depends(get_device_id),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> None:
    _authorized_file(services, file_id, principal=principal, settings=settings, device_id=device_id)
    services.files.delete(file_id, expected_etag=parse_etag(if_match))


@router.post("/{file_id}/restore", response_model=FileObjectRead)
def restore_file(
    file_id: str,
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    device_id: str | None = Depends(get_device_id),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> FileObjectRead:
    _authorized_file_including_deleted(
        services, file_id, principal=principal, settings=settings, device_id=device_id
    )
    return FileObjectRead.from_domain(
        services.files.restore(
            file_id, actor=principal, expected_etag=parse_etag(if_match)
        )
    )


@router.delete("/{file_id}/purge", status_code=204)
def purge_file(
    file_id: str,
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    device_id: str | None = Depends(get_device_id),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> None:
    _authorized_file_including_deleted(
        services, file_id, principal=principal, settings=settings, device_id=device_id
    )
    services.files.purge(
        file_id, actor=principal, expected_etag=parse_etag(if_match)
    )
