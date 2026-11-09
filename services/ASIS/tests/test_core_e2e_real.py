"""Real end-to-end: Tool -> RealCoreAdapter -> CoreDeviceClient -> fake host.

Proves the production path without importing CORE-HOST internals: the
real adapter drives the real stdlib-only device client against the
fake in-process host (same framing + session-token contract), and the
response returns through the real ToolRouter. Also proves local
operation survives CORE loss.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]  # RISARMS checkout root
_CLIENT_MOD = _REPO_ROOT / "CORE-CLIENT" / "client" / "core_device_client.py"
_FAKE_MOD = _REPO_ROOT / "CORE-CLIENT" / "tests" / "fake_host.py"

requires_client_repo = pytest.mark.skipif(
    not (_CLIENT_MOD.exists() and _FAKE_MOD.exists()),
    reason="CORE-CLIENT checkout not adjacent; LAN layout required.",
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def wire(tmp_path):
    client_mod = _load("e2e_core_device_client", _CLIENT_MOD)
    fake_mod = _load("e2e_fake_core_host", _FAKE_MOD)
    host = fake_mod.FakeCoreHost(token="secret-mac-01", device_id="mac-01")
    from asis.integrations.core.adapter import RealCoreAdapter

    def factory(**kw):
        return client_mod.CoreDeviceClient(
            host="127.0.0.1",
            port=host.port,
            device_id="mac-01",
            device_name="MacBook",
            device_file=tmp_path / "device.json",
            use_tls=False,
            timeout=10.0,
        )

    adapter = RealCoreAdapter(client_factory=factory, device_id="mac-01")
    yield host, adapter
    with contextlib.suppress(Exception):
        adapter.disconnect()
    host.stop()


@requires_client_repo
def test_real_adapter_handshake_register_discover(wire):
    host, adapter = wire
    resp = adapter.connect("secret-mac-01")
    assert resp.ok is True, resp.error
    assert adapter.is_connected() is True
    status = adapter.device_status()
    assert status.ok is True
    assert status.data["device_id"] == "mac-01"
    result = adapter.send_request("core", "DEVICE_DISCOVER", {})
    assert result.ok is True
    ids = [d["device_id"] for d in result.data["devices"]]
    assert "mac-01" in ids


@requires_client_repo
def test_real_tool_through_real_router(wire, tmp_path):
    from asis.integrations.core.connection import CoreConnectionManager
    from asis.system.context import RuntimeContext
    from asis.tools.executor import ToolExecutor
    from asis.tools.provided import EchoTool, register_core_tools
    from asis.tools.registry import ToolRegistry
    from asis.tools.router import ToolRouter

    host, adapter = wire
    manager = CoreConnectionManager(
        adapter,
        enabled=True,
        credential_provider=lambda: "secret-mac-01",
        reconnect_enabled=False,
    )
    registry = ToolRegistry()
    registry.register(EchoTool())
    register_core_tools(registry, manager)
    router = ToolRouter(registry, ToolExecutor(authorizer=lambda tool: True))
    ctx = RuntimeContext()
    manager.start(ctx)
    try:
        assert manager.is_available() is True
        result = router.execute("core_discover_devices")
        assert result.success is True, result.error
        blob = json.dumps(result.data)
        assert "mac-01" in blob
        assert "session_token" not in blob
    finally:
        manager.stop(ctx)


@requires_client_repo
def test_real_service_and_data_requests(wire):
    from asis.integrations.core.client import ServiceRequest

    host, adapter = wire
    assert adapter.connect("secret-mac-01").ok is True
    svc = adapter.request_service(
        ServiceRequest(service="health", operation="status", params={})
    )
    assert svc.ok is True
    data = adapter.data_request("record_list", {"namespace": "notes"})
    assert data.ok is True


@requires_client_repo
def test_core_loss_keeps_local_operation(wire):
    from asis.tools.executor import ToolExecutor
    from asis.tools.provided import EchoTool
    from asis.tools.registry import ToolRegistry
    from asis.tools.router import ToolRouter

    host, adapter = wire
    assert adapter.connect("secret-mac-01").ok is True
    host.stop()  # host goes away mid-session
    failed = adapter.send_request("core", "DEVICE_DISCOVER", {}, timeout=2.0)
    assert failed.ok is False
    assert "CORE_" in (failed.error or "")
    # Same-process local path is untouched by the outage.
    registry = ToolRegistry()
    registry.register(EchoTool())
    router = ToolRouter(registry, ToolExecutor(authorizer=lambda tool: True))
    assert router.execute("echo", text="still here").success is True


def test_no_core_host_modules_imported():
    assert not any(name == "core" or name.startswith("core.") for name in sys.modules)


@requires_client_repo
def test_invalid_ca_path_fails_cleanly(tmp_path):
    client_mod = _load("e2e_core_device_client_ca", _CLIENT_MOD)
    fake_mod = _load("e2e_fake_core_host_ca", _FAKE_MOD)
    host = fake_mod.FakeCoreHost(token="secret-mac-01", device_id="mac-01")
    from asis.integrations.core.adapter import RealCoreAdapter

    def factory(**kw):
        return client_mod.CoreDeviceClient(
            host="127.0.0.1",
            port=host.port,
            device_id="mac-01",
            device_name="MacBook",
            device_file=tmp_path / "device.json",
            use_tls=True,  # TLS against plaintext fake + missing CA
            ca_file=tmp_path / "missing.pem",
            timeout=5.0,
        )

    adapter = RealCoreAdapter(client_factory=factory, device_id="mac-01")
    try:
        resp = adapter.connect("secret-mac-01")
        assert resp.ok is False
        assert "CORE_" in (resp.error or "")
        assert adapter.is_connected() is False
    finally:
        adapter.disconnect()
        host.stop()


@requires_client_repo
def test_unresolvable_host_fails_bounded(tmp_path):
    import time

    client_mod = _load("e2e_core_device_client_dns", _CLIENT_MOD)
    from asis.integrations.core.adapter import RealCoreAdapter

    def factory(**kw):
        return client_mod.CoreDeviceClient(
            host="nonexistent.invalid",
            port=5000,
            device_id="mac-01",
            device_name="MacBook",
            device_file=tmp_path / "device.json",
            use_tls=False,
            timeout=8.0,
        )

    adapter = RealCoreAdapter(
        client_factory=factory, device_id="mac-01", connect_timeout=8.0
    )
    started = time.monotonic()
    resp = adapter.connect("secret-mac-01")
    elapsed = time.monotonic() - started
    assert resp.ok is False
    assert elapsed < 60  # bounded: no indefinite DNS/connect hang
    adapter.disconnect()
