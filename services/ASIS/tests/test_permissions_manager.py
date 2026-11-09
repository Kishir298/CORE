"""PermissionManager: named facade over the existing permission primitives."""

from __future__ import annotations

import pytest

from asis.errors import ASISError, PermissionError
from asis.permissions import (
    PermissionLevel,
    PermissionManager,
    auto_approve,
    auto_deny,
)
from asis.tools.executor import ToolExecutor
from asis.tools.provided import EchoTool
from asis.tools.provided.core_tools import (
    CoreDiscoverDevicesTool,
    CoreStatusTool,
)
from asis.tools.registry import ToolRegistry
from asis.tools.router import ToolRouter


def test_allows_safe_tool_without_prompt():
    manager = PermissionManager(handler=auto_deny())
    assert manager.allows(EchoTool()) is True
    assert manager.needs_confirmation(EchoTool()) is False
    assert manager.level(EchoTool()) == PermissionLevel.SAFE


def test_high_tool_needs_confirmation_and_defers_to_handler():
    tool = CoreDiscoverDevicesTool(None)
    assert PermissionManager(handler=auto_approve()).allows(tool) is True
    assert PermissionManager(handler=auto_deny()).allows(tool) is False
    assert PermissionManager(handler=auto_deny()).needs_confirmation(tool) is True


def test_require_raises_asis_permission_error():
    manager = PermissionManager(handler=auto_deny())
    with pytest.raises(PermissionError):
        manager.require(CoreDiscoverDevicesTool(None))
    assert isinstance(PermissionError("x"), ASISError)


def test_authorizer_compatible_with_executor():
    from asis.integrations.core.mock import MockCoreAdapter

    mock = MockCoreAdapter()
    mock.connect()
    manager = PermissionManager(handler=auto_deny())
    registry = ToolRegistry()
    registry.register(CoreStatusTool(mock))
    registry.register(CoreDiscoverDevicesTool(mock))
    router = ToolRouter(registry, ToolExecutor(authorizer=manager.authorizer))
    assert router.execute("core_status").success is True
    denied = router.execute("core_discover_devices")
    assert denied.success is False


def test_explicit_authorizer_passthrough():
    manager = PermissionManager(authorizer=lambda tool: tool.name == "echo")
    assert manager.allows(EchoTool()) is True
    assert manager.allows(CoreStatusTool(None)) is False
