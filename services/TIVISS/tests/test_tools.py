import pytest

from tiviss.permissions import DefaultDenyPolicy, Permission, PermissionContext
from tiviss.tools import (
    EchoTool,
    FailingTool,
    SumTool,
    ToolError,
    ToolRegistry,
    ToolStatus,
    UnknownToolError,
)


@pytest.fixture
def ctx():
    return PermissionContext(source="owner")


@pytest.fixture
def policy():
    return DefaultDenyPolicy(allow={Permission.of("tools.*")})


@pytest.fixture
def registry(policy):
    reg = ToolRegistry(policy=policy)
    reg.register(EchoTool())
    reg.register(SumTool())
    reg.register(FailingTool())
    return reg


def test_registration(registry):
    assert "echo" in registry
    assert len(registry) == 3
    assert registry.get("echo").name == "Echo"


def test_duplicate_registration_rejected(policy):
    registry = ToolRegistry(policy=policy)
    registry.register(EchoTool())
    with pytest.raises(ToolError):
        registry.register(EchoTool())


def test_unknown_tool_raises(registry, ctx):
    with pytest.raises(UnknownToolError):
        registry.execute("does-not-exist", ctx)


def test_echo_execution(registry, ctx):
    result = registry.execute("echo", ctx, {"text": "hello"})
    assert result.status is ToolStatus.OK
    assert result.output == "hello"
    assert result.tool_id == "echo"


def test_sum_execution(registry, ctx):
    result = registry.execute("sum", ctx, {"values": [1, 2, 3]})
    assert result.status is ToolStatus.OK
    assert result.output == 6
    assert result.metadata["count"] == 3


def test_invalid_input_fails(registry, ctx):
    result = registry.execute("sum", ctx, {"values": "not-a-list"})
    assert result.status is ToolStatus.FAILED
    assert "values" in result.error


def test_echo_missing_text_fails(registry, ctx):
    result = registry.execute("echo", ctx, {})
    assert result.status is ToolStatus.FAILED


def test_failing_tool_returns_failed(registry, ctx):
    result = registry.execute("failing", ctx, {})
    assert result.status is ToolStatus.FAILED
    assert "boom" in result.error


def test_permission_denied_returns_denied(ctx):
    registry = ToolRegistry()  # default deny policy
    registry.register(EchoTool())
    result = registry.execute("echo", ctx, {"text": "x"})
    assert result.status is ToolStatus.DENIED
    assert "permission denied" in result.error


def test_permission_change_after_registration():
    policy = DefaultDenyPolicy(allow={Permission.of("tools.echo")})
    registry = ToolRegistry(policy=policy)
    registry.register(EchoTool())
    ctx = PermissionContext(source="owner")
    assert registry.execute("echo", ctx, {"text": "x"}).status is ToolStatus.OK
    policy.revoke_allow("tools.echo")
    assert registry.execute("echo", ctx, {"text": "x"}).status is ToolStatus.DENIED


def test_registry_list_is_sorted(ctx):
    policy = DefaultDenyPolicy(allow={Permission.of("tools.*")})
    registry = ToolRegistry(policy=policy)
    registry.register(SumTool())
    registry.register(EchoTool())
    ids = [tool.tool_id for tool in registry.list()]
    assert ids == ["echo", "sum"]


def test_unregister(registry, ctx):
    assert registry.unregister("echo") is True
    assert registry.unregister("echo") is False
    with pytest.raises(UnknownToolError):
        registry.execute("echo", ctx, {"text": "x"})
