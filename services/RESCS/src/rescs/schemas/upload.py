"""Pydantic schemas for resumable uploads."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from rescs.domain import UploadSessionData
from rescs.schemas.record import _validate_tag_list


class UploadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=512, default="unnamed")
    content_type: str = Field(max_length=128, default="application/octet-stream")
    total_size: int = Field(ge=0)
    chunk_size: int = Field(default=8 * 1024 * 1024, ge=64 * 1024, le=64 * 1024 * 1024)
    checksum: str | None = Field(default=None, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)
    owner: str = Field(default="system", min_length=1, max_length=256)
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, tags: list[str]) -> list[str]:
        return _validate_tag_list(tags)


class UploadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner: str
    filename: str
    content_type: str
    total_size: int
    received_bytes: int
    chunk_size: int
    status: str
    checksum: str | None = None
    created_at: Any
    updated_at: Any
    expires_at: Any
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, data: UploadSessionData) -> UploadRead:
        return cls(**data.to_dict())

