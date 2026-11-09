"""CORE lifecycle: optional connection, bounded retry, runtime integration."""

from __future__ import annotations

from asis.integrations.core.client import CoreResponse
from asis.integrations.core.connection import (
    CoreConnectionManager,
    build_connection_manager_from_settings,
)
from asis.integrations.core.mock import MockCoreAdapter
from asis.integrations.core.models import CoreConnectionState
from asis.system.context import RuntimeContext
from asis.system.runtime import ASISRuntime


class _FailAdapter(MockCoreAdapter):
    def __init__(self):
        super().__init__()
        self.attempts = 0

    def connect(self, credential=None):
        self.attempts += 1
        return CoreResponse(ok=False, error="CORE_UNAVAILABLE: down")


def test_disabled_manager_is_standalone_noop():
    manager = CoreConnectionManager(MockCoreAdapter(), enabled=False)
    ctx = RuntimeContext()
    manager.start(ctx)
    assert manager.state == CoreConnectionState.DISABLED
    assert manager.is_available() is False
    assert manager.request("core", "DEVICE_DISCOVER", {}).ok is False
    manager.stop(ctx)
    assert manager.state == CoreConnectionState.DISABLED


def test_missing_credential_stays_standalone():
    manager = CoreConnectionManager(
        MockCoreAdapter(), enabled=True, credential_provider=lambda: None,
        reconnect_enabled=False,
    )
    ctx = RuntimeContext()
    manager.start(ctx)
    assert manager.state == CoreConnectionState.DISCONNECTED
    assert manager.is_available() is False
    manager.stop(ctx)


def test_successful_connect_registers_context():
    manager = CoreConnectionManager(
        MockCoreAdapter(), enabled=True, credential_provider=lambda: "cred",
        reconnect_enabled=False,
    )
    ctx = RuntimeContext()
    manager.start(ctx)
    assert manager.state == CoreConnectionState.CONNECTED
    assert manager.is_available() is True
    assert ctx.get("core") is manager.adapter
    manager.stop(ctx)
    assert manager.is_available() is False
    assert manager.state == CoreConnectionState.DISCONNECTED


def test_bounded_retries_do_not_hang():
    adapter = _FailAdapter()
    manager = CoreConnectionManager(
        adapter, enabled=True, credential_provider=lambda: "cred",
        reconnect_enabled=True, reconnect_delay=0, max_retries=2,
    )
    ctx = RuntimeContext()
    manager.start(ctx)
    assert adapter.attempts == 3  # 1 initial + 2 retries
    assert manager.state == CoreConnectionState.FAILED
    assert manager.is_available() is False
    manager.stop(ctx)


def test_stop_during_disabled_is_safe():
    manager = CoreConnectionManager(MockCoreAdapter(), enabled=False)
    ctx = RuntimeContext()
    manager.stop(ctx)
    assert manager.state == CoreConnectionState.DISABLED


def test_stop_during_reconnect_backoff_is_bounded():
    import threading
    import time

    adapter = _FailAdapter()
    manager = CoreConnectionManager(
        adapter, enabled=True, credential_provider=lambda: "cred",
        reconnect_enabled=True, reconnect_delay=30, max_retries=5,
    )
    ctx = RuntimeContext()
    worker = threading.Thread(target=manager.start, args=(ctx,), daemon=True)
    started = time.monotonic()
    worker.start()
    time.sleep(0.2)  # let the manager enter the bounded backoff wait
    manager.stop(ctx)
    worker.join(timeout=10)
    elapsed = time.monotonic() - started
    assert not worker.is_alive()  # stop-aware: never sleeps out the 30s backoff
    assert elapsed < 10
    assert manager.state in (
        CoreConnectionState.STOPPING,
        CoreConnectionState.DISCONNECTED,
        CoreConnectionState.DISABLED,
    )


def test_stop_during_request_is_bounded():
    import threading
    import time

    from asis.integrations.core.adapter import RealCoreAdapter

    release = threading.Event()

    class BlockingDevice:
        """Fake device with one blocking in-flight request (no network)."""

        def __init__(self, **kw):
            self.shut_down = False

        def login(self, credential):
            pass

        def connect(self):
            pass

        def register(self):
            pass

        def is_connected(self):
            return not self.shut_down

        def shutdown(self):
            self.shut_down = True
            release.set()

        def request(self, destination, message_type, payload, timeout=30.0):
            release.wait(timeout=min(float(timeout), 5.0))
            return {"message_type": "DATA_RESPONSE", "payload": {"echo": True}}

    adapter = RealCoreAdapter(
        client_factory=lambda **kw: BlockingDevice(**kw),
        request_timeout=30.0,
    )
    assert adapter.connect("cred").ok is True
    results: list = []
    worker = threading.Thread(
        target=lambda: results.append(
            adapter.send_request("core", "DATA_REQUEST", {})
        ),
        daemon=True,
    )
    worker.start()
    time.sleep(0.2)  # let the request go in-flight
    started = time.monotonic()
    adapter.disconnect()
    worker.join(timeout=10)
    elapsed = time.monotonic() - started
    assert not worker.is_alive()  # no indefinite block on shutdown
    assert elapsed < 10
    assert results and results[0].ok is True
    assert adapter.is_connected() is False


def test_runtime_integration_start_stop():
    manager = CoreConnectionManager(
        MockCoreAdapter(), enabled=True, credential_provider=lambda: "cred",
        reconnect_enabled=False,
    )
    runtime = ASISRuntime(components=[manager])
    runtime.start()
    assert runtime.is_running is True
    assert manager.is_available() is True
    runtime.stop()
    assert runtime.is_running is False
    assert manager.is_available() is False


def test_runtime_starts_when_core_down():
    adapter = _FailAdapter()
    manager = CoreConnectionManager(
        adapter, enabled=True, credential_provider=lambda: "cred",
        reconnect_enabled=False,
    )
    runtime = ASISRuntime(components=[manager])
    runtime.start()  # must not raise; local assistant survives
    assert runtime.is_running is True
    runtime.stop()


def test_build_from_settings():
    from types import SimpleNamespace

    core = SimpleNamespace(enabled=True, reconnect_enabled=False, reconnect_delay=1)
    manager = build_connection_manager_from_settings(
        SimpleNamespace(core=core), MockCoreAdapter(), credential_provider=lambda: "c"
    )
    ctx = RuntimeContext()
    manager.start(ctx)
    assert manager.is_available() is True
    manager.stop(ctx)


def test_status_snapshot_offline():
    manager = CoreConnectionManager(MockCoreAdapter(), enabled=False)
    status = manager.status()
    assert status.connected is False
    assert status.state == CoreConnectionState.DISABLED
