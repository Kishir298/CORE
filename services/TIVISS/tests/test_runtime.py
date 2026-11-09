import pytest

from tiviss.agent import Agent, AgentState, LifecycleTransitionError
from tiviss.conversation import Request, ResponseStatus
from tiviss.events import EventBus, EventType
from tiviss.identity import AgentIdentity
from tiviss.models import MockProvider
from tiviss.permissions import DefaultDenyPolicy, Permission


@pytest.fixture
def identity():
    return AgentIdentity.create(
        agent_id="tiviss-test", name="tiviss", version="0.1.0", owner_id="kishir"
    )


@pytest.fixture
def provider():
    return MockProvider()


@pytest.fixture
def policy():
    return DefaultDenyPolicy(allow={Permission.of("conversation.generate")})


@pytest.fixture
def bus():
    return EventBus()


def make_agent(identity, provider, policy=None, bus=None):
    return Agent(identity=identity, provider=provider, policy=policy, event_bus=bus)


def test_agent_initial_state_is_created(identity, provider):
    agent = make_agent(identity, provider)
    assert agent.state is AgentState.CREATED
    assert not agent.is_running


def test_start_moves_to_running(identity, provider):
    agent = make_agent(identity, provider)
    agent.start()
    assert agent.state is AgentState.RUNNING
    assert agent.is_running


def test_stop_moves_to_stopped(identity, provider):
    agent = make_agent(identity, provider)
    agent.start()
    agent.stop()
    assert agent.state is AgentState.STOPPED


def test_restart_after_stop_fails(identity, provider):
    agent = make_agent(identity, provider)
    agent.start()
    agent.stop()
    with pytest.raises(LifecycleTransitionError):
        agent.start()


def test_status(identity, provider):
    agent = make_agent(identity, provider)
    agent.start()
    status = agent.status()
    assert status.state is AgentState.RUNNING
    assert status.agent_id == "tiviss-test"
    assert status.model_id == "tiviss-mock-1"
    assert status.requests_handled == 0
    assert status.started_at is not None


def test_invalid_transition_double_start(identity, provider):
    agent = make_agent(identity, provider)
    agent.start()
    with pytest.raises(LifecycleTransitionError):
        agent.start()


def test_invalid_transition_stop_before_start(identity, provider):
    agent = make_agent(identity, provider)
    with pytest.raises(LifecycleTransitionError):
        agent.stop()


def test_start_emits_event(identity, provider, bus):
    agent = make_agent(identity, provider, bus=bus)
    started = []
    bus.subscribe(lambda e: started.append(e), EventType.AGENT_STARTED)
    agent.start()
    assert len(started) == 1
    assert started[0].payload["agent_id"] == "tiviss-test"


def test_stop_emits_event(identity, provider, bus):
    agent = make_agent(identity, provider, bus=bus)
    stopped = []
    bus.subscribe(lambda e: stopped.append(e), EventType.AGENT_STOPPED)
    agent.start()
    agent.stop()
    assert len(stopped) == 1


def test_process_returns_ok_response(identity, provider, policy):
    agent = make_agent(identity, provider, policy=policy)
    agent.start()
    request = Request.create(source="owner", content="ping")
    response = agent.process(request)
    assert response.status is ResponseStatus.OK
    assert response.agent_id == "tiviss-test"
    assert response.request_id == request.request_id
    assert response.ok
    assert "ping" in response.content


def test_process_without_permission_is_denied(identity, provider):
    agent = make_agent(identity, provider, policy=DefaultDenyPolicy())
    agent.start()
    request = Request.create(source="owner", content="ping")
    response = agent.process(request)
    assert response.status is ResponseStatus.DENIED
    assert response.ok is False


def test_process_denied_emits_permission_event(identity, provider, bus):
    agent = make_agent(identity, provider, policy=DefaultDenyPolicy(), bus=bus)
    denied = []
    bus.subscribe(lambda e: denied.append(e), EventType.PERMISSION_DENIED)
    agent.start()
    agent.process(Request.create(source="owner", content="ping"))
    assert len(denied) == 1
    assert denied[0].payload["permission"] == "conversation.generate"


def test_process_requires_running(identity, provider, policy):
    agent = make_agent(identity, provider, policy=policy)
    with pytest.raises(LifecycleTransitionError):
        agent.process(Request.create(source="owner", content="ping"))


def test_process_stores_memory(identity, provider, policy):
    from tiviss.memory import LocalMemory

    memory = LocalMemory()
    agent = Agent(identity=identity, provider=provider, policy=policy, memory=memory)
    agent.start()
    request = Request.create(source="owner", content="remember this")
    agent.process(request)
    assert memory.metadata()["stored"] == 1
    status = agent.status()
    assert status.memory_stored == 1
    assert status.requests_handled == 1


def test_process_provider_failure_returns_failed(identity):
    provider = MockProvider(failure_mode=True)
    policy = DefaultDenyPolicy(allow={Permission.of("conversation.generate")})
    agent = make_agent(identity, provider, policy=policy)
    agent.start()
    response = agent.process(Request.create(source="owner", content="x"))
    assert response.status is ResponseStatus.FAILED
    assert response.ok is False
