from tiviss.events import Event, EventBus, EventType


def _count(container):
    return len(container)


def test_event_creation():
    event = Event.create(
        type=EventType.AGENT_STARTED, source="agent:1", payload={"x": 1}
    )
    assert event.type is EventType.AGENT_STARTED
    assert event.source == "agent:1"
    assert event.payload == {"x": 1}
    assert event.event_id
    assert event.timestamp.tzinfo is not None
    assert event.metadata == {}


def test_event_type_known_values():
    assert EventType.AGENT_STARTED.value == "agent.started"
    assert EventType.HANDOVER_REQUESTED.value == "handover.requested"
    assert EventType.OWNERSHIP_CHANGED.value == "ownership.changed"
    assert EventType.PERMISSION_DENIED.value == "permission.denied"


def test_bus_publish_calls_all_handler():
    bus = EventBus()
    received = []
    bus.subscribe(lambda event: received.append(event))
    event = Event.create(type=EventType.GENERIC, source="s")
    bus.publish(event)
    assert received == [event]
    assert len(bus.published) == 1


def test_bus_typed_subscription():
    bus = EventBus()
    started, stopped = [], []
    bus.subscribe(lambda e: started.append(e), EventType.AGENT_STARTED)
    bus.subscribe(lambda e: stopped.append(e), EventType.AGENT_STOPPED)

    bus.publish(Event.create(type=EventType.AGENT_STARTED, source="s"))
    bus.publish(Event.create(type=EventType.AGENT_STOPPED, source="s"))

    assert len(started) == 1
    assert len(stopped) == 1


def test_bus_unsubscribe():
    bus = EventBus()
    received = []

    def handler(e):
        return received.append(e)

    bus.subscribe(handler)
    assert bus.unsubscribe(handler) is True
    bus.publish(Event.create(type=EventType.GENERIC, source="s"))
    assert received == []


def test_bus_unsubscribe_unknown_returns_false():
    bus = EventBus()
    assert bus.unsubscribe(lambda e: None) is False


def test_event_metadata_preserved():
    event = Event.create(
        type=EventType.MEMORY_STORED,
        source="s",
        payload={"record_id": "r1"},
        metadata={"trace": "abc"},
    )
    assert event.metadata == {"trace": "abc"}


def test_handler_failure_is_captured():
    bus = EventBus()
    captured = []

    def bad_handler(event):
        raise RuntimeError("boom")

    bus.subscribe(bad_handler, EventType.GENERIC)
    bus.subscribe(lambda e: captured.append(e), EventType.GENERIC)

    event = Event.create(type=EventType.GENERIC, source="s")
    published = bus.publish(event)

    assert published is event
    assert len(captured) == 1
    assert len(bus.errors) == 1
    assert isinstance(bus.errors[0][1], RuntimeError)


def test_handler_error_callback():
    seen = []

    def on_error(event, exc):
        seen.append(exc)

    bus = EventBus(handler_error=on_error)
    bus.subscribe(
        lambda e: (_ for _ in ()).throw(ValueError("nope")), EventType.GENERIC
    )
    bus.publish(Event.create(type=EventType.GENERIC, source="s"))
    assert len(seen) == 1
    assert isinstance(seen[0], ValueError)
