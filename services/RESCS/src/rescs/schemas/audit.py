"""Pydantic schemas for audit event inspection."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from rescs.domain import AuditData


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    timestamp: Any
    operation: str
    resource_type: str
    resource_id: str | None = None
    owner: str
    request_id: str | None = None
    outcome: str
    error_code: str | None = None

    @classmethod
    def from_domain(cls, data: AuditData) -> AuditRead:
        return cls(**data.to_dict())


class AuditPage(BaseModel):
    items: list[AuditRead]
    total: int
    limit: int
    offset: int

