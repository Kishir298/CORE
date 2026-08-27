import pytest

from core.runtime import Runtime, RuntimeError, RuntimeState


def test_runtime_starts_and_stops():
    runtime = Runtime()

    runtime.start()

    assert runtime.state == RuntimeState.RUNNING

    runtime.stop()

    assert runtime.state == RuntimeState.STOPPED


def test_runtime_initializes_components():
    runtime = Runtime()
    initialized = []

    def initialize():
        initialized.append("component")

    runtime.register_component(
        "test",
        initialize,
    )

    runtime.start()

    assert initialized == ["component"]
    assert runtime.state == RuntimeState.RUNNING


def test_runtime_component_shutdown():
    runtime = Runtime()
    events = []

    def initialize():
        events.append("start")

    def shutdown():
        events.append("stop")

    runtime.register_component(
        "test",
        initialize,
        shutdown,
    )

    runtime.start()
    runtime.stop()

    assert events == ["start", "stop"]


def test_shutdown_runs_in_reverse_order():
    runtime = Runtime()
    events = []

    runtime.register_component(
        "first",
        lambda: events.append("first-start"),
        lambda: events.append("first-stop"),
    )

    runtime.register_component(
        "second",
        lambda: events.append("second-start"),
        lambda: events.append("second-stop"),
    )

    runtime.start()
    runtime.stop()

    assert events == [
        "first-start",
        "second-start",
        "second-stop",
        "first-stop",
    ]


def test_start_is_idempotent():
    runtime = Runtime()
    count = 0

    def initialize():
        nonlocal count
        count += 1

    runtime.register_component(
        "test",
        initialize,
    )

    runtime.start()
    runtime.start()

    assert count == 1
    assert runtime.state == RuntimeState.RUNNING


def test_stop_is_idempotent():
    runtime = Runtime()
    count = 0

    def shutdown():
        nonlocal count
        count += 1

    runtime.register_component(
        "test",
        lambda: None,
        shutdown,
    )

    runtime.start()
    runtime.stop()
    runtime.stop()

    assert count == 1
    assert runtime.state == RuntimeState.STOPPED


def test_restart():
    runtime = Runtime()
    events = []

    runtime.register_component(
        "test",
        lambda: events.append("start"),
        lambda: events.append("stop"),
    )

    runtime.start()
    runtime.restart()

    assert runtime.state == RuntimeState.RUNNING
    assert events == [
        "start",
        "stop",
        "start",
    ]


def test_failed_initialization():
    runtime = Runtime()

    def broken_initializer():
        raise ValueError("broken component")

    runtime.register_component(
        "broken",
        broken_initializer,
    )

    with pytest.raises(RuntimeError):
        runtime.start()

    assert runtime.state == RuntimeState.FAILED
    assert runtime.error is not None


def test_failed_component_shutdown_does_not_stop_other_shutdowns():
    runtime = Runtime()
    events = []

    runtime.register_component(
        "first",
        lambda: None,
        lambda: events.append("first"),
    )

    def broken_shutdown():
        raise RuntimeError("shutdown failed")

    runtime.register_component(
        "broken",
        lambda: None,
        broken_shutdown,
    )

    runtime.register_component(
        "last",
        lambda: None,
        lambda: events.append("last"),
    )

    runtime.start()
    runtime.stop()

    assert runtime.state == RuntimeState.STOPPED
    assert "first" in events
    assert "last" in events


def test_component_count():
    runtime = Runtime()

    runtime.register_component(
        "one",
        lambda: None,
    )

    runtime.register_component(
        "two",
        lambda: None,
    )

    assert runtime.component_count() == 2


def test_clear_components():
    runtime = Runtime()

    runtime.register_component(
        "one",
        lambda: None,
    )

    runtime.clear_components()

    assert runtime.component_count() == 0


def test_cannot_clear_active_runtime():
    runtime = Runtime()

    runtime.register_component(
        "one",
        lambda: None,
    )

    runtime.start()

    with pytest.raises(RuntimeError):
        runtime.clear_components()


def test_invalid_start_state():
    runtime = Runtime()

    runtime._state = RuntimeState.INITIALIZING

    with pytest.raises(RuntimeError):
        runtime.start()


def test_error_is_cleared_on_successful_restart():
    runtime = Runtime()

    attempts = 0

    def initializer():
        nonlocal attempts
        attempts += 1

        if attempts == 1:
            raise ValueError("temporary failure")

    runtime.register_component(
        "test",
        initializer,
    )

    with pytest.raises(RuntimeError):
        runtime.start()

    assert runtime.state == RuntimeState.FAILED

    runtime.start()

    assert runtime.state == RuntimeState.RUNNING
    assert runtime.error is None
