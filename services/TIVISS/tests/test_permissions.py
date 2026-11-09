import pytest

from tiviss.identity import AgentIdentity
from tiviss.permissions import (
    DefaultDenyPolicy,
    Permission,
    PermissionContext,
    PermissionDeniedError,
    PermissionValidationError,
)


@pytest.fixture
def identity():
    return AgentIdentity.create(name="tiviss", version="0.1.0", owner_id="kishir")


def test_permission_string_representation():
    assert str(Permission.of("memory.store")) == "memory.store"
    assert str(Permission.of("memory.store")) == "memory.store"


def test_permission_equality_and_hash():
    a, b = Permission.of("memory.store"), Permission.of("memory.store")
    assert a == b
    assert hash(a) == hash(b)


def test_permission_wildcard_matches():
    pattern = Permission.of("memory.*")
    assert pattern.is_pattern()
    assert pattern.matches(Permission.of("memory.store"))
    assert pattern.matches(Permission.of("memory.delete"))
    assert not pattern.matches(Permission.of("tools.run"))


def test_permission_exact_matches_only_exact():
    exact = Permission.of("memory.store")
    assert exact.matches(Permission.of("memory.store"))
    assert not exact.matches(Permission.of("memory.delete"))
    assert not exact.matches(Permission.of("memory.store.extra"))


def test_permission_invalid_name_rejected():
    with pytest.raises(PermissionValidationError):
        Permission.of("")
    with pytest.raises(PermissionValidationError):
        Permission.of("not valid")
    with pytest.raises(PermissionValidationError):
        Permission.of("*.all")


def test_default_deny_policy_denies_by_default():
    policy = DefaultDenyPolicy()
    ctx = PermissionContext(source="owner")
    assert policy.check(ctx, Permission.of("memory.store")) is False


def test_allowed_operation():
    policy = DefaultDenyPolicy(allow={Permission.of("memory.store")})
    ctx = PermissionContext(source="owner")
    assert policy.check(ctx, Permission.of("memory.store")) is True


def test_denied_operation():
    policy = DefaultDenyPolicy(
        allow={Permission.of("memory.*")}, deny={Permission.of("memory.delete")}
    )
    ctx = PermissionContext(source="owner")
    assert policy.check(ctx, Permission.of("memory.store")) is True
    assert policy.check(ctx, Permission.of("memory.delete")) is False


def test_missing_permission_raises():
    policy = DefaultDenyPolicy()
    ctx = PermissionContext(source="owner")
    with pytest.raises(PermissionDeniedError) as excinfo:
        policy.assert_allowed(ctx, Permission.of("tools.run"))
    assert "tools.run" in str(excinfo.value)


def test_wildcard_allow():
    policy = DefaultDenyPolicy(allow={Permission.of("memory.*")})
    ctx = PermissionContext(source="owner")
    assert policy.check(ctx, Permission.of("memory.anything")) is True


def test_allow_and_deny_mutators():
    policy = DefaultDenyPolicy()
    policy.allow("conversation.generate")
    ctx = PermissionContext(source="owner")
    assert policy.check(ctx, Permission.of("conversation.generate")) is True
    policy.deny("conversation.generate")
    assert policy.check(ctx, Permission.of("conversation.generate")) is False
    policy.revoke_allow("conversation.generate")
    assert policy.check(ctx, Permission.of("conversation.generate")) is False


def test_permission_identity_context(identity):
    policy = DefaultDenyPolicy(allow={Permission.of("memory.*")})
    ctx = PermissionContext(source="handover", identity=identity)
    assert policy.check(ctx, Permission.of("memory.store")) is True
    assert ctx.identity.agent_id == identity.agent_id
