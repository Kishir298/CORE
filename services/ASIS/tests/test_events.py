"""Tests for the event bus."""

from __future__ import annotations

from asis.events import Event, EventBus, EventType


def test_subscribe_and_publish():
    bus = EventBus()
    received = []

    def handler(event):
        received.append(event)

    bus.subscribe(EventType.MEMORY_SAVED, handler)
    bus.publish(Event(type=EventType.MEMORY_SAVED, data={"n": 1}, source="test"))

    assert len(received) == 1
    assert received[0].data == {"n": 1}
    assert received[0].source == "test"


def test_publish_ignores_unsubscribed_event():
    bus = EventBus()
    received = []

    def handler(event):
        received.append(event)

    bus.subscribe(EventType.SYSTEM_STARTED, handler)
    bus.publish(Event(type=EventType.SYSTEM_STOPPED, source="test"))

    assert received == []


def test_unsubscribe_removes_handler():
    bus = EventBus()

    def handler(event):
        pass

    bus.subscribe(EventType.SYSTEM_STARTED, handler)
    assert bus.subscriber_count(EventType.SYSTEM_STARTED) == 1

    bus.unsubscribe(EventType.SYSTEM_STARTED, handler)
    assert bus.subscriber_count(EventType.SYSTEM_STARTED) == 0


def test_subscriber_count_unknown_is_zero():
    bus = EventBus()
    assert bus.subscriber_count(EventType.ERROR_OCCURRED) == 0


def test_clear_removes_all_handlers():
    bus = EventBus()

    def handler(event):
        pass

    bus.subscribe(EventType.MEMORY_SAVED, handler)
    bus.subscribe(EventType.MEMORY_DELETED, handler)

    bus.clear()

    assert bus.subscriber_count(EventType.MEMORY_SAVED) == 0
    assert bus.subscriber_count(EventType.MEMORY_DELETED) == 0
