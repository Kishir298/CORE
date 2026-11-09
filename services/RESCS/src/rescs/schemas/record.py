"""Pydantic schemas for record storage operations."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from rescs.domain import MAX_TAG_LENGTH, MAX_TAGS, RecordData

_TAG_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_tag_list(tags: list[str]) -> list[str]:
    stripped = [tag.strip() for tag in tags]
    if len(stripped) > MAX_TAGS:
        raise ValueError(f"at most {MAX_TAGS} tags are allowed")
    for tag in stripped:
        if not tag or len(tag) > MAX_TAG_LENGTH or not _TAG_PATTERN.match(tag):
            raise ValueError(
                f"invalid tag {tag!r}; 1-{MAX_TAG_LENGTH} chars of [A-Za-z0-9._-] expected"
            )
    return stripped


def _is_json_serializable(value: Any) -> bool:
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return False
    return True


class _JsonFieldMixin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _payloads_must_be_json(self):
        for field_name in ("value", "metadata"):
            value = getattr(self, field_name, None)
            if value is not None and not _is_json_serializable(value):
                raise ValueError(
                    f"{field_name} contains values that are not JSON-serializable"
                )
        return self


class RecordCreate(_JsonFieldMixin):
    namespace: str = Field(default="default", max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    key: str = Field(min_length=1, max_length=512)
    value: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
    owner: str = Field(default="system", min_length=1, max_length=256)
    idempotency_key: str | None = Field(default=None, max_length=128)
    tags: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    ttl_seconds: int | None = None

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, tags: list[str]) -> list[str]:
        return _validate_tag_list(tags)

    @field_validator("ttl_seconds")
    @classmethod
    def _validate_ttl(cls, ttl: int | None) -> int | None:
        if ttl is not None and ttl < 1:
            raise ValueError("ttl_seconds must be >= 1")
        return ttl

    @model_validator(mode="after")
    def _expiry_not_ambiguous(self):
        if self.expires_at is not None and self.ttl_seconds is not None:
            raise ValueError("set either expires_at or ttl_seconds, not both")
        return self


class RecordUpdate(_JsonFieldMixin):
    value: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    namespace: str | None = Field(default=None, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    key: str | None = Field(default=None, min_length=1, max_length=512)
    tags: list[str] | None = None
    expires_at: datetime | None = None
    ttl_seconds: int | None = None

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, tags: list[str] | None) -> list[str] | None:
        if tags is None:
            return None
        return _validate_tag_list(tags)

    @field_validator("ttl_seconds")
    @classmethod
    def _validate_ttl(cls, ttl: int | None) -> int | None:
        if ttl is not None and ttl < 1:
            raise ValueError("ttl_seconds must be >= 1")
        return ttl

    @model_validator(mode="after")
    def _expiry_not_ambiguous(self):
        if self.expires_at is not None and self.ttl_seconds is not None:
            raise ValueError("set either expires_at or ttl_seconds, not both")
        return self


class RecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    namespace: str
    key: str
    value: dict[str, Any]
    metadata: dict[str, Any]
    owner: str
    version: int
    idempotency_key: str | None = None
    etag: str
    created_at: Any
    updated_at: Any
    tags: list[str] = Field(default_factory=list)
    expires_at: Any = None
    deleted_at: Any = None
    deleted_by: str | None = None

    @classmethod
    def from_domain(cls, data: RecordData) -> RecordRead:
        return cls(**data.to_dict())


class RecordPage(BaseModel):
    items: list[RecordRead]
    total: int
    limit: int
    offset: int


class BulkItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: str
    id: str | None = None
    record: RecordCreate | None = None
    if_match: str | None = Field(default=None, alias="if_match")

    @model_validator(mode="after")
    def _check_shape(self):
        if self.op in ("create", "put") and self.record is None:
            raise ValueError(f"bulk op {self.op!r} requires a record payload")
        if self.op in ("delete", "restore", "purge") and not self.id:
            raise ValueError(f"bulk op {self.op!r} requires an id")
        return self


class BulkRequest(BaseModel):
    operations: list[BulkItem] = Field(min_length=1, max_length=1000)


class BulkResultItem(BaseModel):
    index: int
    status: str
    id: str | None = None
    code: str | None = None
    message: str | None = None
    details: Any = None


class BulkResponse(BaseModel):
    results: list[BulkResultItem]
