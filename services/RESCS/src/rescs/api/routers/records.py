"""Record storage API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Response

from rescs.api.deps import get_services, get_settings, parse_etag
from rescs.config import Settings
from rescs.schemas.record import (
    BulkRequest,
    BulkResponse,
    BulkResultItem,
    RecordCreate,
    RecordPage,
    RecordRead,
    RecordUpdate,
)
from rescs.security import (
    assert_device_ownership,
    assert_principal_is_owner,
    enforce_owner,
    get_device_id,
    require_api_key,
    scoped_query_owner,
    validate_device_namespace,
    validate_device_owner,
)
from rescs.services.factory import Services

router = APIRouter(
    prefix="/records",
    tags=["records"],
    dependencies=[Depends(require_api_key)],
)


def _page(
    services: Services,
    *,
    namespace: str | None,
    key_prefix: str | None,
    owner: str | None,
    query: str | None,
    limit: int,
    offset: int,
    tags: list[str] | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    updated_after: datetime | None = None,
    updated_before: datetime | None = None,
    include_deleted: bool = False,
    include_expired: bool = False,
) -> RecordPage:
    if query:
        page = services.records.search(
            query=query,
            namespace=namespace,
            owner=owner,
            limit=limit,
            offset=offset,
            tags=tags,
            include_deleted=include_deleted,
            include_expired=include_expired,
        )
    else:
        page = services.records.list(
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
    return RecordPage(
        items=[RecordRead.from_domain(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


def _apply_etag_header(response: Response, record) -> None:
    response.headers["ETag"] = record.etag


def _apply_device_scope(
    *,
    namespace: str | None,
    owner: str | None,
    device_id: str | None,
    operation: str,
) -> tuple[str | None, str | None]:
    """Apply device-scoped validation/transformation to namespace and owner."""
    if device_id is None:
        return namespace, owner
    if namespace is not None:
        namespace = validate_device_namespace(namespace, device_id, operation)
    if owner is not None:
        owner = validate_device_owner(owner, device_id, operation)
    return namespace, owner


@router.post("", status_code=201, response_model=RecordRead)
def create_record(
    payload: RecordCreate,
    response: Response,
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    device_id: str | None = Depends(get_device_id),
) -> RecordRead:
    payload.owner = enforce_owner(
        requested=payload.owner, principal=principal, settings=settings
    )
    payload.namespace, payload.owner = _apply_device_scope(
        namespace=payload.namespace,
        owner=payload.owner,
        device_id=device_id,
        operation="create record",
    )
    record = RecordRead.from_domain(services.records.create(payload))
    _apply_etag_header(response, record)
    return record


@router.put("", response_model=RecordRead, summary="Create or replace by namespace/key")
def put_record(
    payload: RecordCreate,
    response: Response,
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    device_id: str | None = Depends(get_device_id),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> RecordRead:
    payload.owner = enforce_owner(
        requested=payload.owner, principal=principal, settings=settings
    )
    payload.namespace, payload.owner = _apply_device_scope(
        namespace=payload.namespace,
        owner=payload.owner,
        device_id=device_id,
        operation="put record",
    )
    record = RecordRead.from_domain(
        services.records.put(payload, expected_etag=parse_etag(if_match))
    )
    _apply_etag_header(response, record)
    return record


@router.get("", response_model=RecordPage)
def list_records(
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    device_id: str | None = Depends(get_device_id),
    namespace: str | None = Query(default=None),
    key_prefix: str | None = Query(default=None),
    owner: str | None = Query(default=None),
    query: str | None = Query(default=None, description="Full-text-ish search"),
    tags: list[str] | None = Query(default=None),
    created_after: datetime | None = Query(default=None),
    created_before: datetime | None = Query(default=None),
    updated_after: datetime | None = Query(default=None),
    updated_before: datetime | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    include_expired: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> RecordPage:
    owner = scoped_query_owner(owner=owner, principal=principal, settings=settings)
    namespace, owner = _apply_device_scope(
        namespace=namespace,
        owner=owner,
        device_id=device_id,
        operation="list records",
    )
    return _page(
        services,
        namespace=namespace,
        key_prefix=key_prefix,
        owner=owner,
        query=query,
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


def _authorized_record(
    services: Services,
    record_id: str,
    *,
    principal: str,
    settings: Settings,
    device_id: str | None = None,
) -> Any:
    record = services.records.get(record_id)
    assert_principal_is_owner(
        record_owner=record.owner, principal=principal, settings=settings
    )
    if device_id is not None:
        assert_device_ownership(
            resource_owner=record.owner,
            resource_namespace=record.namespace,
            device_id=device_id,
            operation="read record",
        )
    return record


def _authorized_record_including_deleted(
    services: Services,
    record_id: str,
    *,
    principal: str,
    settings: Settings,
    device_id: str | None = None,
) -> Any:
    record = services.records.get_including_deleted(record_id)
    assert_principal_is_owner(
        record_owner=record.owner, principal=principal, settings=settings
    )
    if device_id is not None:
        assert_device_ownership(
            resource_owner=record.owner,
            resource_namespace=record.namespace,
            device_id=device_id,
            operation="read record",
        )
    return record


@router.get("/{record_id}", response_model=RecordRead)
def get_record(
    record_id: str,
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    device_id: str | None = Depends(get_device_id),
) -> RecordRead:
    return RecordRead.from_domain(
        _authorized_record(
            services, record_id, principal=principal, settings=settings, device_id=device_id
        )
    )


@router.patch("/{record_id}", response_model=RecordRead)
def update_record(
    record_id: str,
    payload: RecordUpdate,
    response: Response,
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    device_id: str | None = Depends(get_device_id),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> RecordRead:
    _authorized_record(
        services, record_id, principal=principal, settings=settings, device_id=device_id
    )
    record = RecordRead.from_domain(
        services.records.update(
            record_id, payload, expected_etag=parse_etag(if_match)
        )
    )
    _apply_etag_header(response, record)
    return record


@router.delete("/{record_id}", status_code=204)
def delete_record(
    record_id: str,
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    device_id: str | None = Depends(get_device_id),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> None:
    _authorized_record(
        services, record_id, principal=principal, settings=settings, device_id=device_id
    )
    services.records.delete(record_id, expected_etag=parse_etag(if_match))


@router.post("/{record_id}/restore", response_model=RecordRead)
def restore_record(
    record_id: str,
    response: Response,
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    device_id: str | None = Depends(get_device_id),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> RecordRead:
    _authorized_record_including_deleted(
        services, record_id, principal=principal, settings=settings, device_id=device_id
    )
    record = RecordRead.from_domain(
        services.records.restore(
            record_id, actor=principal, expected_etag=parse_etag(if_match)
        )
    )
    _apply_etag_header(response, record)
    return record


@router.delete("/{record_id}/purge", status_code=204)
def purge_record(
    record_id: str,
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    device_id: str | None = Depends(get_device_id),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> None:
    _authorized_record_including_deleted(
        services, record_id, principal=principal, settings=settings, device_id=device_id
    )
    services.records.purge(
        record_id, actor=principal, expected_etag=parse_etag(if_match)
    )


@router.post("/bulk", response_model=BulkResponse)
def bulk_records(
    payload: BulkRequest,
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_settings),
    principal: str = Depends(require_api_key),
    device_id: str | None = Depends(get_device_id),
) -> BulkResponse:
    operations: list[dict[str, Any]] = []
    for item in payload.operations:
        entry: dict[str, Any] = {"op": item.op}
        if item.id is not None:
            entry["id"] = item.id
        if item.record is not None:
            record_payload = item.record
            record_payload.owner = enforce_owner(
                requested=record_payload.owner,
                principal=principal,
                settings=settings,
            )
            record_payload.namespace, record_payload.owner = _apply_device_scope(
                namespace=record_payload.namespace,
                owner=record_payload.owner,
                device_id=device_id,
                operation="bulk record",
            )
            entry["record"] = record_payload.model_dump()
        if item.if_match is not None:
            entry["if_match"] = parse_etag(item.if_match)
        operations.append(entry)
    results = services.records.bulk(operations, actor=principal)
    return BulkResponse(results=[BulkResultItem(**result) for result in results])
