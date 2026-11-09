"""Conversation contracts: request/response message models.

These are independent of C.O.R.E.'s messaging implementation. A future
adapter can translate between T.I.V.I.S.S. messages and C.O.R.E. messages.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class RequestValidationError(ValueError):
    """Raised when a request is invalid."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Request:
    """A single request directed at the agent."""

    request_id: str
    source: str
    content: str
    timestamp: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        source: str,
        content: str,
        request_id: str | None = None,
        timestamp: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Request:
        errors = []
        if not (isinstance(source, str) and source.strip()):
            errors.append("source must be a non-empty string")
        if not (isinstance(content, str) and content.strip()):
            errors.append("content must be a non-empty string")
        if timestamp is not None:
            if not isinstance(timestamp, datetime):
                errors.append("timestamp must be a datetime")
            elif timestamp.tzinfo is None or timestamp.utcoffset() is None:
                errors.append("timestamp must be timezone-aware")
        if errors:
            raise RequestValidationError("; ".join(errors))
        return cls(
            request_id=request_id or str(uuid.uuid4()),
            source=source,
            content=content,
            timestamp=timestamp or _utcnow(),
            metadata=dict(metadata or {}),
        )


class ResponseStatus(StrEnum):
    """Outcome of handling a request."""

    OK = "ok"
    DENIED = "denied"
    FAILED = "failed"
    ERROR = "error"


@dataclass(frozen=True)
class Response:
    """A response produced by the agent for a request."""

    request_id: str
    agent_id: str
    content: str
    timestamp: datetime
    status: ResponseStatus
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        request_id: str,
        agent_id: str,
        content: str,
        status: ResponseStatus,
        timestamp: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Response:
        return cls(
            request_id=request_id,
            agent_id=agent_id,
            content=content,
            timestamp=timestamp or _utcnow(),
            status=ResponseStatus(status),
            metadata=dict(metadata or {}),
        )

    @property
    def ok(self) -> bool:
        return self.status is ResponseStatus.OK
