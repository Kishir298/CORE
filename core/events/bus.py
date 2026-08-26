from collections import defaultdict
from collections.abc import Callable

from .models import Event


EventHandler = Callable[[Event], None]


class EventBus:
    """Central event bus for C.O.R.E."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> None:
        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)

    def unsubscribe(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> None:
        subscribers = self._subscribers.get(event_type)

        if not subscribers:
            return

        if handler in subscribers:
            subscribers.remove(handler)

        if not subscribers:
            del self._subscribers[event_type]

    def publish(self, event: Event) -> None:
        for handler in list(self._subscribers.get(event.event_type, [])):
            handler(event)

    def emit(
        self,
        event_type: str,
        source: str,
        payload: dict | None = None,
    ) -> Event:
        event = Event(
            event_type=event_type,
            source=source,
            payload=payload or {},
        )

        self.publish(event)
        return event

    def clear(self) -> None:
        self._subscribers.clear()

    def subscriber_count(self, event_type: str | None = None) -> int:
        if event_type is not None:
            return len(self._subscribers.get(event_type, []))

        return sum(
            len(subscribers)
            for subscribers in self._subscribers.values()
        )
