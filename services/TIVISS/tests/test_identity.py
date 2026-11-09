from datetime import UTC, datetime

import pytest

from tiviss.identity import AgentIdentity, IdentityState, IdentityValidationError


def test_identity_creation_generates_stable_id():
    identity = AgentIdentity.create(name="tiviss", version="0.1.0", owner_id="kishir")
    assert isinstance(identity.agent_id, str)
    assert identity.agent_id
    assert identity.agent_id == identity.agent_id


def test_identity_creation_with_explicit_id_is_stable():
    identity = AgentIdentity.create(
        agent_id="tiviss-0001", name="tiviss", version="0.1.0", owner_id="kishir"
    )
    assert identity.agent_id == "tiviss-0001"


def test_identity_creation_defaults():
    identity = AgentIdentity.create(name="tiviss", version="0.1.0", owner_id="kishir")
    assert identity.state is IdentityState.ACTIVE
    assert identity.created_at.tzinfo is not None
    assert identity.meta == {}


def test_identity_is_stable_across_model_changes():
    identity = AgentIdentity.create(
        agent_id="tiviss-x", name="tiviss", version="0.1.0", owner_id="kishir"
    )
    assert identity.agent_id == "tiviss-x"
    assert identity.version == "0.1.0"


def test_identity_validation_rejects_empty_name():
    with pytest.raises(IdentityValidationError):
        AgentIdentity.create(name="", version="0.1.0", owner_id="kishir")


def test_identity_validation_rejects_empty_version():
    with pytest.raises(IdentityValidationError):
        AgentIdentity.create(name="tiviss", version="", owner_id="kishir")


def test_identity_validation_rejects_empty_owner():
    with pytest.raises(IdentityValidationError):
        AgentIdentity.create(name="tiviss", version="0.1.0", owner_id="")


def test_identity_validation_rejects_unknown_state():
    with pytest.raises(IdentityValidationError):
        AgentIdentity.create(
            name="tiviss", version="0.1.0", owner_id="kishir", state="flying"
        )


def test_identity_validation_rejects_naive_timestamp():
    with pytest.raises(IdentityValidationError):
        AgentIdentity.create(
            name="tiviss",
            version="0.1.0",
            owner_id="kishir",
            created_at=datetime(2026, 1, 1),
        )


def test_identity_validation_accepts_aware_timestamp():
    identity = AgentIdentity.create(
        name="tiviss",
        version="0.1.0",
        owner_id="kishir",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert identity.created_at == datetime(2026, 1, 1, tzinfo=UTC)


def test_identity_state_enum_values():
    assert IdentityState.ACTIVE.value == "active"
    assert IdentityState.SUSPENDED.value == "suspended"
    assert IdentityState.RETIRED.value == "retired"


def test_identity_validation_of_existing_record():
    identity = AgentIdentity.create(
        agent_id="tiviss-1", name="tiviss", version="0.1.0", owner_id="k"
    )
    assert AgentIdentity.validate_identity(identity) == []
