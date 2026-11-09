"""CORE tools: registry integration, permissions, offline safety, size limits."""

from __future__ import annotations

import json

from asis.integrations.core.mock import MockCoreAdapter
from asis.permissions.models import PermissionLevel
from asis.tools.executor import ToolExecutor
from asis.tools.provided.core_tools import (
    build_core_tools,
    register_core_tools,
)
from asis.tools.registry import ToolRegistry
from asis.tools.router import ToolRouter


def _online_mock():
    mock = MockCoreAdapter()
    mock.connect()
    return mock


def test_core_tools_register_on_shared_registry():
    registry = ToolRegistry()
    names = register_core_tools(registry, MockCoreAdapter())
    assert names == [
        "core_discover_devices",
        "core_device_info",
        "core_status",
        "core_data_request",
        "core_service_request",
        "core_agent_request",
        "core_send_to_device",
    ]
    assert "core_discover_devices" in registry.list_names()


def test_network_tools_require_confirmation_level():
    tools = {t.name: t for t in build_core_tools(MockCoreAdapter())}
    for name in (
        "core_discover_devices",
        "core_device_info",
        "core_data_request",
        "core_service_request",
        "core_agent_request",
        "core_send_to_device",
    ):
        assert tools[name].permission >= PermissionLevel.HIGH, name
    assert tools["core_status"].permission == PermissionLevel.SAFE


def test_offline_tools_fail_cleanly():
    registry = ToolRegistry()
    register_core_tools(registry, MockCoreAdapter())  # never connected
    router = ToolRouter(registry, ToolExecutor(authorizer=lambda tool: True))
    for name, kwargs in (
        ("core_discover_devices", {}),
        ("core_device_info", {"device_id": "mac-01"}),
        ("core_data_request", {"request_type": "record_list"}),
        ("core_service_request", {"service": "health", "operation": "status"}),
        ("core_agent_request", {"operation": "status"}),
        ("core_send_to_device", {"device_id": "mac-02", "message_type": "APP_PING"}),
    ):
        result = router.execute(name, **kwargs)
        assert result.success is False, name
        assert "CORE_UNAVAILABLE" in (result.error or ""), name


def test_online_discover_and_status():
    registry = ToolRegistry()
    register_core_tools(registry, _online_mock())
    router = ToolRouter(registry, ToolExecutor(authorizer=lambda tool: True))
    assert router.execute("core_discover_devices").success is True
    status = router.execute("core_status")
    assert status.success is True
    assert status.data["connected"] is True


def test_device_info_validates_args():
    registry = ToolRegistry()
    register_core_tools(registry, _online_mock())
    router = ToolRouter(registry, ToolExecutor(authorizer=lambda tool: True))
    bad = router.execute("core_device_info")
    assert bad.success is False
    assert "device_id" in (bad.error or "")
    good = router.execute("core_device_info", device_id="mac-01")
    assert good.success is True


def test_service_and_agent_validation():
    registry = ToolRegistry()
    register_core_tools(registry, _online_mock())
    router = ToolRouter(registry, ToolExecutor(authorizer=lambda tool: True))
    assert router.execute("core_service_request").success is False
    ok = router.execute("core_service_request", service="health", operation="status")
    # Mock has no service handlers -> honest failure, still structured.
    assert ok.success is False
    assert "Mock C.O.R.E." in (ok.error or "")
    agent = router.execute("core_agent_request", operation="status")
    assert agent.success is False


def test_permission_denial_never_touches_core():
    seen = []

    class SpyMock(MockCoreAdapter):
        def send_request(self, *a, **k):
            seen.append((a, k))
            return super().send_request(*a, **k)

    registry = ToolRegistry()
    register_core_tools(registry, SpyMock())
    router = ToolRouter(registry, ToolExecutor(authorizer=lambda tool: False))
    result = router.execute("core_discover_devices")
    assert result.success is False
    assert seen == []


def test_oversized_results_truncated_before_model():
    mock = _online_mock()
    mock.set_resource("big", {"blob": "y" * 50_000})
    registry = ToolRegistry()
    register_core_tools(registry, mock)
    assert "core_discover_devices" in registry.list_names()
    # Resource path normalizes through the size bound.
    resp = mock.get_resource("big")
    assert resp.ok is True
    text = json.dumps(resp.data)
    assert len(text) <= 9_000


def test_no_credentials_in_tool_results():
    registry = ToolRegistry()
    register_core_tools(registry, _online_mock())
    router = ToolRouter(registry, ToolExecutor(authorizer=lambda tool: True))
    for name, kwargs in (
        ("core_discover_devices", {}),
        ("core_device_info", {"device_id": "mac-01"}),
        ("core_data_request", {"request_type": "record_list"}),
        ("core_send_to_device", {"device_id": "mac-02", "message_type": "APP_PING"}),
        ("core_status", {}),
    ):
        result = router.execute(name, **kwargs)
        blob = json.dumps(
            {"ok": result.success, "data": result.data, "err": result.error}
        )
        for secret in ("session_token", "credential", "connection_id"):
            assert secret not in blob, (name, secret)


def test_data_request_validates_args():
    registry = ToolRegistry()
    register_core_tools(registry, _online_mock())
    router = ToolRouter(registry, ToolExecutor(authorizer=lambda tool: True))
    assert router.execute("core_data_request").success is False
    assert (
        router.execute("core_data_request", request_type="record_list").success is True
    )
    bad = router.execute("core_data_request", request_type="x", params="nope")
    assert bad.success is False
    assert "params" in (bad.error or "")


def test_send_to_device_validates_args():
    registry = ToolRegistry()
    register_core_tools(registry, _online_mock())
    router = ToolRouter(registry, ToolExecutor(authorizer=lambda tool: True))
    assert router.execute("core_send_to_device").success is False
    assert router.execute("core_send_to_device", device_id="mac-02").success is False
    ok = router.execute(
        "core_send_to_device", device_id="mac-02", message_type="APP_PING"
    )
    assert ok.success is True
