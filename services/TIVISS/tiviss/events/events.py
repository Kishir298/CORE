"""Local event model and synchronous event bus.

Events are local and independent of C.O.R.E.'s EventBus. A future adapter can
forward these events to the ecosystem.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(UTC)


class EventType(StrEnum):
    """Well-known T.I.V.I.S.S. event types."""

    AGENT_STARTED = "agent.started"
    AGENT_STOPPED = "agent.stopped"
    AGENT_STATUS = "agent.status"

    MEMORY_STORED = "memory.stored"
    MEMORY_RETRIEVED = "memory.retrieved"
    MEMORY_DELETED = "memory.deleted"
    MEMORY_CLEARED = "memory.cleared"

    PERMISSION_DENIED = "permission.denied"

    HANDOVER_REQUESTED = "handover.requested"
    HANDOVER_APPROVED = "handover.approved"
    HANDOVER_REJECTED = "handover.rejected"
    HANDOVER_CANCELLED = "handover.cancelled"
    HANDOVER_COMPLETED = "handover.completed"

    OWNERSHIP_CHANGED = "ownership.changed"
    OWNERSHIP_REVOKED = "ownership.revoked"

    TOOL_EXECUTED = "tool.executed"
    TOOL_FAILED = "tool.failed"

    CORE_REGISTERED = "core.registered"
    CORE_DISCONNECTED = "core.disconnected"

    RESCS_SYNCED = "rescs.synced"
    RESCS_ERROR = "rescs.error"

    GENERIC = "generic"


EventSubscriber = Callable[["Event"], None]


@dataclass(frozen=True)
class Event:
    """An immutable event record."""

    event_id: str
    type: EventType
    source: str
    timestamp: datetime
    payload: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        type: EventType | str,
        source: str,
        payload: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        event_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> Event:
        return cls(
            event_id=event_id or str(uuid.uuid4()),
            type=EventType(type),
            source=source,
            timestamp=timestamp or _utcnow(),
            payload=dict(payload or {}),
            metadata=dict(metadata or {}),
        )


class EventBus:
    """A simple synchronous, local event bus.

    Handler failures are captured and routed to the optional error handler
    instead of propagating, so one bad handler cannot break dispatch.
    """

    def __init__(
        self, *, handler_error: Callable[[Event, Exception], None] | None = None,
        max_events: int | None = 10000,
    ) -> None:
        if max_events is not None:
            if isinstance(max_events, bool) or not isinstance(max_events, int):
                raise TypeError("max_events must be a positive int or None")
            if max_events <= 0:
                raise ValueError("max_events must be positive")
        self._all_handlers: list[EventSubscriber] = []
        self._typed_handlers: dict[EventType, list[EventSubscriber]] = {}
        self._handler_error = handler_error
        self.max_events = max_events
        self.published: list[Event] = []
        self.errors: list[tuple[Event, Exception]] = []

    def subscribe(
        self, handler: EventSubscriber, event_type: EventType | None = None
    ) -> None:
        """Register a handler for all events or a single event type."""
        if event_type is None:
            if handler not in self._all_handlers:
                self._all_handlers.append(handler)
            return
        event_type = EventType(event_type)
        handlers = self._typed_handlers.setdefault(event_type, [])
        if handler not in handlers:
            handlers.append(handler)

    def unsubscribe(
        self, handler: EventSubscriber, event_type: EventType | None = None
    ) -> bool:
        """Remove a handler. Returns True when a handler was removed."""
        if event_type is None:
            try:
                self._all_handlers.remove(handler)
            except ValueError:
                return False
        else:
            handlers = self._typed_handlers.get(EventType(event_type))
            if not handlers:
                return False
            try:
                handlers.remove(handler)
            except ValueError:
                return False
        return True

    def publish(self, event: Event) -> Event:
        """Dispatch an event synchronously to all matching handlers."""
        self.published.append(event)
        # Bound retained history so a long-lived bus cannot grow without
        # limit (default 10k; oldest events are dropped first).
        if self.max_events is not None and len(self.published) > self.max_events:
            del self.published[: len(self.published) - self.max_events]
        handlers = list(self._all_handlers) + list(
            self._typed_handlers.get(event.type, [])
        )
        # de-duplicate handlers (all-handler + typed registration)
        seen: list[EventSubscriber] = []
        for handler in handlers:
            if handler not in seen:
                seen.append(handler)
        for handler in seen:
            try:
                handler(event)
            except Exception as exc:  # noqa: BLE001 - route handler failures deliberately
                self.errors.append((event, exc))
                if self._handler_error is not None:
                    self._handler_error(event, exc)
        return event

    def emit(self, event: Event) -> Event:
        """Alias for :meth:`publish`."""
        return self.publish(event)

    def clear(self) -> None:
        """Clear recorded published events and errors (handlers stay registered)."""
        self.published.clear()
        self.errors.clear()
