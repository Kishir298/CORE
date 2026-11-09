"""Deterministic tests for runtime shutdown timeout enforcement."""

from __future__ import annotations

import time

import pytest

from asis.system.component import RuntimeComponent
from asis.system.context import RuntimeContext
from asis.system.runtime import ASISRuntime
from asis.system.state import RuntimeState


class FastComponent(RuntimeComponent):
    name = "fast"

    def __init__(self):
        self.events: list[str] = []

    def start(self, context: RuntimeContext) -> None:
        self.events.append("start")

    def stop(self, context: RuntimeContext) -> None:
        self.events.append("stop")


class SlowComponent(RuntimeComponent):
    name = "slow"

    def start(self, context: RuntimeContext) -> None:
        pass

    def stop(self, context: RuntimeContext) -> None:
        time.sleep(30)


class OrderComponent(RuntimeComponent):
    stopped: list[str] = []

    def __init__(self, name: str):
        self.name = name

    def start(self, context: RuntimeContext) -> None:
        pass

    def stop(self, context: RuntimeContext) -> None:
        OrderComponent.stopped.append(self.name)


def test_normal_shutdown_within_timeout():
    fast = FastComponent()
    runtime = ASISRuntime([fast])
    runtime.start()
    runtime.stop(timeout=2)
    assert runtime.state == RuntimeState.STOPPED
    assert fast.events == ["start", "stop"]


def test_slow_component_timeout_does_not_hang():
    runtime = ASISRuntime([SlowComponent()])
    runtime.start()
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        runtime.stop(timeout=0.1)
    elapsed = time.monotonic() - started
    assert elapsed < 5
    assert runtime.state == RuntimeState.FAILED


def test_reverse_order_shutdown_preserved():
    OrderComponent.stopped = []
    runtime = ASISRuntime([OrderComponent("a"), OrderComponent("b")])
    runtime.start()
    runtime.stop(timeout=2)
    assert OrderComponent.stopped == ["b", "a"]


def test_shutdown_cancels_interrupt_scopes():

    runtime = ASISRuntime([FastComponent()])
    runtime.start()
    runtime.interrupts.register("inference")
    runtime.interrupts.register("voice")
    runtime.stop(timeout=2)
    assert runtime.interrupts.is_cancelled("inference")
    assert runtime.interrupts.is_cancelled("voice")


def test_shutdown_failure_state_consistent():
    """Per-component stop errors are contained; shutdown still completes.

    LifecycleManager.stop_all preserves reverse-order best-effort
    semantics (log + continue), so a single bad component does not abort
    the remaining shutdown. Runtime therefore reaches STOPPED.
    """

    class BadStop(RuntimeComponent):
        name = "bad"

        def start(self, context: RuntimeContext) -> None:
            pass

        def stop(self, context: RuntimeContext) -> None:
            raise RuntimeError("stop failed")

    runtime = ASISRuntime([BadStop()])
    runtime.start()
    runtime.stop(timeout=2)
    assert runtime.state == RuntimeState.STOPPED
