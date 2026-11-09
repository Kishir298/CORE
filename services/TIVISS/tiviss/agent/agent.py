"""The T.I.V.I.S.S. agent runtime.

The runtime owns the lifecycle (start/stop/status), request handling, and the
wiring of identity, provider, memory, permissions, events, and tools. It does
not perform unrestricted autonomous actions: every request passes through the
permission layer before a provider is consulted.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ..conversation.messages import Request, Response, ResponseStatus
from ..events.events import Event, EventBus, EventType
from ..identity.identity import AgentIdentity
from ..memory.interface import MemoryBackend, MemoryKeyError, MemoryRecord
from ..models.provider import ModelProvider, ProviderError
from ..permissions.permissions import (
    Permission,
    PermissionContext,
    PermissionDeniedError,
)
from ..permissions.policy import DefaultDenyPolicy, PermissionPolicy
from .lifecycle import LifecycleManager
from .state import AgentState, LifecycleTransitionError

PERMISSION_GENERATE = Permission.of("conversation.generate")


@dataclass
class AgentStatus:
    """Snapshot of the runtime status."""

    state: AgentState
    agent_id: str
    model_id: str
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    requests_handled: int = 0
    memory_stored: int = 0


class Agent:
    """T.I.V.I.S.S. agent runtime facade."""

    def __init__(
        self,
        *,
        identity: AgentIdentity,
        provider: ModelProvider,
        memory: MemoryBackend | None = None,
        policy: PermissionPolicy | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.identity = identity
        self.provider = provider
        self.memory = memory
        self.policy = policy or DefaultDenyPolicy()
        self.events = event_bus or EventBus()

        self.lifecycle = LifecycleManager()
        self.started_at: datetime | None = None
        self.stopped_at: datetime | None = None
        self.requests_handled = 0
        self.memory_stored = 0

    @property
    def state(self) -> AgentState:
        return self.lifecycle.state

    @property
    def is_running(self) -> bool:
        return self.lifecycle.is_running

    def _emit(self, type_: EventType, **payload: Any) -> Event:
        return self.events.publish(
            Event.create(
                type=type_, source=f"agent:{self.identity.agent_id}", payload=payload
            )
        )

    def start(self) -> None:
        """Initialize and start the runtime."""
        if self.state is AgentState.CREATED:
            self.lifecycle.transition(AgentState.READY)
        if self.state is AgentState.READY:
            self.lifecycle.transition(AgentState.RUNNING)
        else:
            raise LifecycleTransitionError(self.state, AgentState.RUNNING)
        self.started_at = self._now()
        self._emit(EventType.AGENT_STARTED, agent_id=self.identity.agent_id)

    def stop(self) -> None:
        """Stop the runtime through a controlled shutdown."""
        if self.state is AgentState.READY or self.state is AgentState.RUNNING:
            self.lifecycle.transition(AgentState.STOPPING)
            self.lifecycle.transition(AgentState.STOPPED)
        else:
            raise LifecycleTransitionError(self.state, AgentState.STOPPED)
        self.stopped_at = self._now()
        self._emit(EventType.AGENT_STOPPED, agent_id=self.identity.agent_id)

    def status(self) -> AgentStatus:
        """Return a status snapshot."""
        return AgentStatus(
            state=self.state,
            agent_id=self.identity.agent_id,
            model_id=self.provider.model_id if self.provider else "none",
            started_at=self.started_at,
            stopped_at=self.stopped_at,
            requests_handled=self.requests_handled,
            memory_stored=self.memory_stored,
        )

    def process(
        self, request: Request, *, timeout_s: float | None = None
    ) -> Response:
        """Handle one request. Returns a structured response; never raises for
        expected failures (permission denied, provider failure, agent stopped).

        ``timeout_s`` is an optional per-request timeout in seconds passed
        through to the provider. Invalid values surface as a ``FAILED``
        response with ``reason`` ``provider_error``.
        """
        self.lifecycle.require(AgentState.RUNNING)

        if not self._authorized(request):
            return Response.create(
                request_id=request.request_id,
                agent_id=self.identity.agent_id,
                content="request not permitted",
                status=ResponseStatus.DENIED,
                metadata={"reason": "permission_denied"},
            )

        try:
            model_response = self.provider.generate(
                request.content,
                context=dict(request.metadata),
                timeout_s=timeout_s,
            )
        except ProviderError as exc:
            return Response.create(
                request_id=request.request_id,
                agent_id=self.identity.agent_id,
                content=str(exc),
                status=ResponseStatus.FAILED,
                metadata={"reason": "provider_error"},
            )

        self.requests_handled += 1
        response = Response.create(
            request_id=request.request_id,
            agent_id=self.identity.agent_id,
            content=model_response.content,
            status=ResponseStatus.OK,
            metadata={
                "provider_id": model_response.provider_id,
                "model_id": model_response.model_id,
            },
        )

        if self.memory is not None:
            with contextlib.suppress(MemoryKeyError):
                self._remember(request)
        return response

    def _authorized(self, request: Request) -> bool:
        ctx = PermissionContext(source=request.source, identity=self.identity)
        try:
            self.policy.assert_allowed(ctx, PERMISSION_GENERATE)
            return True
        except PermissionDeniedError:
            self._emit(
                EventType.PERMISSION_DENIED,
                permission=PERMISSION_GENERATE.name,
                source=request.source,
            )
            return False

    def _remember(self, request: Request) -> None:
        record = MemoryRecord(
            key=f"request:{request.request_id}",
            content=request.content,
            metadata={"source": request.source, "request_id": request.request_id},
        )
        self.memory.store(record)
        self.memory_stored += 1
        self._emit(EventType.MEMORY_STORED, record_id=record.record_id, key=record.key)

    @staticmethod
    def _now() -> datetime:

        return datetime.now(UTC)
