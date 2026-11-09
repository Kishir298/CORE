"""
Thread-safe synchronous event bus for A.S.I.S.

Components publish and subscribe without knowing which other components
are listening. This is the local event surface today and will later be
bridged to C.O.R.E. through the CoreAdapter.
"""

from __future__ import annotations

import threading
from collections import defaultdict

from asis.logging.logger import get_logger

from .events import Event, EventType
from .handlers import EventHandler


class EventBus:
    """Thread-safe event dispatcher."""

    def __init__(self) -> None:
        self._logger = get_logger("events")
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Subscribe a handler to an event type."""
        with self._lock:
            if handler not in self._handlers[event_type]:
                self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Remove a handler from an event type."""
        with self._lock:
            handlers = self._handlers.get(event_type, [])

            if handler in handlers:
                handlers.remove(handler)

    def publish(self, event: Event) -> None:
        """Publish an event to every subscribed handler."""
        with self._lock:
            handlers = list(self._handlers.get(event.type, []))

        for handler in handlers:
            try:
                handler(event)
            except Exception:
                self._logger.exception(
                    "Event handler failed for %s",
                    event.type.value,
                )

    def clear(self) -> None:
        """Remove all subscriptions."""
        with self._lock:
            self._handlers.clear()

    def subscriber_count(self, event_type: EventType) -> int:
        """Return the number of subscribers for an event type."""
        with self._lock:
            return len(self._handlers.get(event_type, []))
