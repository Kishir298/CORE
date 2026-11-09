"""C.O.R.E. integration adapter (interface + local mock).

Provides the contract for future T.I.V.I.S.S. <-> C.O.R.E. communication:
register agent, report health, publish events, send/receive requests. The
local implementation is an in-memory mock transport so the contract is
testable without the C.O.R.E. repository.

This adapter does NOT duplicate C.O.R.E. functionality.
"""

from __future__ import annotations

from abc import ABC
from collections.abc import Mapping
from typing import Any

from ..configuration.config import CoreSettings
from ..conversation.messages import Request
from ..events.events import Event
from ..identity.identity import AgentIdentity
from ..models.provider import ProviderError  # noqa: F401  (re-export convenience)
from .base import (
    IntegrationAdapter,
    IntegrationRequest,
    IntegrationResponse,
    IntegrationStatus,
)


class COREAdapter(IntegrationAdapter, ABC):
    """Interface to a future C.O.R.E. connection."""

    adapter_id = "core.adapter"

    def register_agent(self, identity: AgentIdentity) -> IntegrationResponse:
        raise NotImplementedError

    def report_health(self, status: Mapping[str, Any]) -> IntegrationResponse:
        raise NotImplementedError

    def publish_event(self, event: Event) -> IntegrationResponse:
        raise NotImplementedError

    def send_request(self, request: Request) -> IntegrationResponse:
        raise NotImplementedError


class LocalCOREAdapter(COREAdapter):
    """In-memory mock transport for the C.O.R.E. contract.

    Records every interaction for inspection and echoes deterministic
    responses. Set ``fail_next`` to simulate a remote failure.
    """

    adapter_id = "core.local"

    def __init__(self, *, failure_mode: bool = False) -> None:
        self._failure_mode = failure_mode
        self._connected = False
        self.registered: list[AgentIdentity] = []
        self.health_reports: list[Mapping[str, Any]] = []
        self.events_published: list[Event] = []
        self.requests: list[Request] = []

    def connect(self, *, authorized: bool = False) -> bool:
        """Establish the mock connection (requires explicit authorization)."""
        if not authorized:
            return False
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def connected(self) -> bool:
        return self._connected

    def health(self) -> Mapping[str, Any]:
        return {
            "adapter": self.adapter_id,
            "connected": self._connected,
            "failure_mode": self._failure_mode,
            "registered_agents": len(self.registered),
            "published_events": len(self.events_published),
        }

    def _response(
        self,
        request: IntegrationRequest,
        *,
        ok: bool,
        status: IntegrationStatus | None = None,
        payload: Mapping[str, Any] | None = None,
        error: str | None = None,
    ) -> IntegrationResponse:
        if self._failure_mode:
            return IntegrationResponse(
                request_id=request.request_id,
                status=IntegrationStatus.ERROR,
                error="core adapter is in failure mode",
            )
        if not self._connected:
            return self._unavailable(request)
        return IntegrationResponse(
            request_id=request.request_id,
            status=status or (IntegrationStatus.OK if ok else IntegrationStatus.ERROR),
            payload=dict(payload or {}),
            error=error,
        )

    def register_agent(self, identity: AgentIdentity) -> IntegrationResponse:
        request = IntegrationRequest(
            operation="register_agent",
            payload={"agent_id": identity.agent_id},
            source=identity.agent_id,
        )
        # Check failure/connection BEFORE mutating local state so failure
        # mode never records agents it reports as failed.
        if self._failure_mode:
            return self._response(request, ok=True, payload={})
        if not self.connected():
            return self._unavailable(request)
        self.registered.append(identity)
        return self._response(
            request,
            ok=True,
            payload={"status": "registered", "agent_id": identity.agent_id},
        )

    def report_health(self, status: Mapping[str, Any]) -> IntegrationResponse:
        request = IntegrationRequest(
            operation="report_health",
            payload=dict(status),
            source=status.get("agent_id", "unknown"),
        )
        if self._failure_mode:
            return self._response(request, ok=True, payload={})
        if not self.connected():
            return self._unavailable(request)
        self.health_reports.append(dict(status))
        return self._response(request, ok=True, payload={"acknowledged": True})

    def publish_event(self, event: Event) -> IntegrationResponse:
        request = IntegrationRequest(
            operation="publish_event",
            payload={"event_type": event.type.value, "event_id": event.event_id},
            source=event.source,
        )
        if self._failure_mode:
            return self._response(request, ok=True, payload={})
        if not self.connected():
            return self._unavailable(request)
        self.events_published.append(event)
        return self._response(request, ok=True, payload={"event_id": event.event_id})

    def send_request(self, request: Request) -> IntegrationResponse:
        transport = IntegrationRequest(
            operation="send_request",
            payload={"content": request.content},
            source=request.source,
        )
        if self._failure_mode:
            return self._response(transport, ok=True, payload={})
        if not self.connected():
            return self._unavailable(transport)
        self.requests.append(request)
        return self._response(
            transport,
            ok=True,
            payload={
                "content": f"core-echo: {request.content}",
                "correlates": transport.request_id,
            },
        )

    @classmethod
    def from_config(cls, config: CoreSettings) -> LocalCOREAdapter:
        """Build a local adapter from C.O.R.E. integration settings."""
        return cls(failure_mode=not config.enabled)


import json

MAX_RESULT_CHARS = 8_000


def normalize_result(data: Any, max_chars: int = MAX_RESULT_CHARS) -> Any:
    """Redact then bound the size of a host response for model consumption."""
    from .base import redact
    cleaned = redact(data)
    try:
        text = json.dumps(cleaned, default=str)
    except Exception:
        text = str(cleaned)
    if len(text) <= max_chars:
        return cleaned
    truncated = text[:max_chars]
    return {"truncated": True, "max_chars": max_chars, "preview": truncated}
