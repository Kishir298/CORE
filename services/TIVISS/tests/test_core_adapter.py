"""C.O.R.E. integration adapter tests (local mock transport, no external deps)."""

import pytest

from tiviss.conversation import Request
from tiviss.events import Event, EventType
from tiviss.identity import AgentIdentity
from tiviss.integrations import IntegrationStatus, LocalCOREAdapter


@pytest.fixture
def identity():
    return AgentIdentity.create(
        agent_id="tiviss-int", name="tiviss", version="0.1.0", owner_id="kishir"
    )


@pytest.fixture
def core():
    return LocalCOREAdapter()


def test_core_connect_requires_authorization(core):
    assert core.connect(authorized=False) is False
    assert core.connected() is False


def test_core_connect_with_authorization(core):
    assert core.connect(authorized=True) is True
    assert core.connected() is True


def test_core_health(core):
    core.connect(authorized=True)
    health = core.health()
    assert health["adapter"] == "core.local"
    assert health["connected"] is True


def test_core_register_agent(core, identity):
    core.connect(authorized=True)
    response = core.register_agent(identity)
    assert response.ok
    assert response.payload["agent_id"] == "tiviss-int"
    assert len(core.registered) == 1


def test_core_report_health(core, identity):
    core.connect(authorized=True)
    response = core.report_health({"agent_id": identity.agent_id, "state": "running"})
    assert response.ok
    assert len(core.health_reports) == 1


def test_core_publish_event(core, identity):
    core.connect(authorized=True)
    event = Event.create(type=EventType.AGENT_STARTED, source=identity.agent_id)
    response = core.publish_event(event)
    assert response.ok
    assert len(core.events_published) == 1


def test_core_send_request(core, identity):
    core.connect(authorized=True)
    request = Request.create(source=identity.agent_id, content="hello")
    response = core.send_request(request)
    assert response.ok
    assert response.payload["content"] == "core-echo: hello"
    assert len(core.requests) == 1


def test_core_operation_while_disconnected(core, identity):
    response = core.register_agent(identity)
    assert response.status is IntegrationStatus.NOT_AVAILABLE
    assert not response.ok


def test_core_failure_mode(core, identity):
    core.connect(authorized=True)
    core._failure_mode = True
    response = core.report_health({"agent_id": "x", "state": "running"})
    assert response.status is IntegrationStatus.ERROR
