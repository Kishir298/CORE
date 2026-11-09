"""Shared integration adapter contracts.

These adapters represent FUTURE connectivity and must never be confused with a
live integration. They are treated as untrusted boundaries until explicitly
authorized and configured.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def utcnow() -> datetime:
    return datetime.now(UTC)


REDACTED_KEYS = frozenset(
    {
        "token",
        "credential",
        "password",
        "api_token",
        "session",
        "session_token",
        "_session_token",
        "connection_id",
        "authenticated",
    }
)

REDACTED = "***REDACTED***"


def redact(value: Any) -> Any:
    """Recursively replace secret-bearing keys with a placeholder."""
    if isinstance(value, dict):
        return {
            key: (REDACTED if key in REDACTED_KEYS else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        cleaned = [redact(item) for item in value]
        return type(value)(cleaned) if isinstance(value, tuple) else cleaned
    return value


class IntegrationStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    DENIED = "denied"
    NOT_AVAILABLE = "not_available"


@dataclass(frozen=True)
class IntegrationRequest:
    """A request emitted by T.I.V.I.S.S. toward an external system."""

    operation: str
    payload: Mapping[str, Any]
    source: str
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=utcnow)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IntegrationResponse:
    """A response received back from an external system."""

    request_id: str
    status: IntegrationStatus
    payload: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None
    timestamp: datetime = field(default_factory=utcnow)

    @property
    def ok(self) -> bool:
        return self.status is IntegrationStatus.OK


class IntegrationAdapter(ABC):
    """Base contract for an external integration boundary."""

    adapter_id: str = "integration.base"

    @abstractmethod
    def connect(self, *, authorized: bool = False) -> bool:
        """Establish a connection. ``authorized`` must be explicit."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection."""

    @abstractmethod
    def connected(self) -> bool:
        """Whether the adapter currently holds a connection."""

    @abstractmethod
    def health(self) -> Mapping[str, Any]:
        """Report adapter health/status."""

    def _unavailable(self, request: IntegrationRequest) -> IntegrationResponse:
        return IntegrationResponse(
            request_id=request.request_id,
            status=IntegrationStatus.NOT_AVAILABLE,
            error="adapter is not connected or not available",
        )
