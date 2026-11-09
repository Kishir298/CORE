"""AssistantApp CORE layer: explicit core: commands on the shared pipeline."""

from __future__ import annotations

from asis.ai import AIManager
from asis.ai.providers import MockAIProvider
from asis.app import AssistantApp, parse_core_intent
from asis.app.assistant import build_default_tool_router
from asis.identity import build_identity
from asis.integrations.core.connection import CoreConnectionManager
from asis.integrations.core.mock import MockCoreAdapter
from asis.system.context import RuntimeContext
from asis.tools.executor import ToolExecutor
from asis.tools.provided import register_core_tools
from asis.tools.registry import ToolRegistry
from asis.tools.router import ToolRouter


def _app(memory_manager, responses=("hello local",), core=None, router=None):
    return AssistantApp(
        identity=build_identity(),
        ai=AIManager(provider=MockAIProvider(responses=list(responses))),
        memory=memory_manager,
        tools_router=router,
        core=core,
    )


def _online_stack():
    mock = MockCoreAdapter()
    manager = CoreConnectionManager(
        mock, enabled=True, credential_provider=lambda: "cred",
        reconnect_enabled=False,
    )
    registry = ToolRegistry()
    register_core_tools(registry, manager)
    router = ToolRouter(registry, ToolExecutor(authorizer=lambda tool: True))
    return manager, router


def test_local_chat_unaffected_by_core_layer(memory_manager):
    app = _app(memory_manager)
    assert app.chat("hi there") == "hello local"
    assert app.core_available is False


def test_core_command_offline_reports_unavailable(memory_manager):
    manager, router = _online_stack()  # never started -> offline
    app = _app(memory_manager, core=manager, router=router)
    reply = app.chat("core:devices")
    assert "CORE_UNAVAILABLE" in reply
    # Local inference was bypassed, but the turn is still recorded.
    assert app.session.last() is not None


def test_core_command_online_runs_tool(memory_manager):
    manager, router = _online_stack()
    ctx = RuntimeContext()
    manager.start(ctx)
    try:
        app = _app(memory_manager, core=manager, router=router)
        assert "core_discover_devices: ok" in app.chat("core:devices")
        assert "core_device_info" in app.chat("core:device mac-01")
        assert "core_status" in app.chat("core:status")
    finally:
        manager.stop(ctx)


def test_core_tools_registered_on_default_router(memory_manager):
    manager, _ = _online_stack()
    app = _app(memory_manager, core=manager)
    assert "core_discover_devices" in app.tools_router.registry.list_names()


def test_core_tools_registered_on_coding_router(memory_manager):
    manager, _ = _online_stack()
    ctx = RuntimeContext()
    manager.start(ctx)
    try:
        app = _app(memory_manager, core=manager)
        app.set_mode("coding")
        assert "core_discover_devices" in app.tools_router.registry.list_names()
        assert app.tools_router is not app._general_router
    finally:
        manager.stop(ctx)


def test_core_command_in_coding_mode_uses_same_adapter(memory_manager):
    manager, router = _online_stack()
    ctx = RuntimeContext()
    manager.start(ctx)
    try:
        app = _app(memory_manager, core=manager, router=router)
        app.set_mode("coding")
        assert app.mode.value == "coding"
        assert "core_status" in app.chat("core:status")
        assert app._coding_router is not None
        assert manager.adapter is not None
        assert manager.is_available() is True  # still the ONE connection
    finally:
        manager.stop(ctx)


def test_parse_core_intent_matrix():
    assert parse_core_intent("hello") is None
    assert parse_core_intent("core:") is None
    assert parse_core_intent("core:bogus") is None
    assert parse_core_intent("core:device") is None  # missing id
    assert parse_core_intent("core:devices").tool_name == "core_discover_devices"
    assert parse_core_intent("core:status").tool_name == "core_status"
    assert parse_core_intent("core:device mac-01").kwargs == {"device_id": "mac-01"}
    svc = parse_core_intent("core:service health status")
    assert svc.tool_name == "core_service_request"
    assert parse_core_intent("core:agent status").tool_name == "core_agent_request"
    data = parse_core_intent("core:data record_list")
    assert data.tool_name == "core_data_request"
    send = parse_core_intent("core:send mac-02 APP_PING hello")
    assert send.tool_name == "core_send_to_device"
    assert send.kwargs["device_id"] == "mac-02"


def test_core_status_text_offline_and_disabled(memory_manager):
    assert "disabled" in _app(memory_manager).core_status_text()
    manager, _ = _online_stack()
    assert "disconnected" in _app(memory_manager, core=manager).core_status_text()


def test_default_router_builder_still_local_only():
    router = build_default_tool_router()
    assert "core_discover_devices" not in router.registry.list_names()
