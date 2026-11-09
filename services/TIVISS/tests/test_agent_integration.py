"""Cross-component integration coverage.

These tests wire subsystems together (identity + runtime + memory + provider +
permissions + events + handover + adapters) to prove the architecture works
as a whole without any external service.
"""

import pytest

from tiviss.agent import Agent, AgentState
from tiviss.conversation import Request, ResponseStatus
from tiviss.events import EventBus, EventType
from tiviss.handover import Handover
from tiviss.identity import AgentIdentity, Ownership, OwnershipState
from tiviss.integrations import LocalCOREAdapter, LocalRESCSAdapter
from tiviss.memory import LocalMemory
from tiviss.models import MockProvider
from tiviss.permissions import DefaultDenyPolicy, Permission


@pytest.fixture
def identity():
    return AgentIdentity.create(
        agent_id="tiviss-integration", name="tiviss", version="0.1.0", owner_id="kishir"
    )


@pytest.fixture
def events():
    return EventBus()


@pytest.fixture
def memory():
    return LocalMemory()


def build_agent(identity, events, memory):
    provider = MockProvider()
    policy = DefaultDenyPolicy(
        allow={Permission.of("conversation.generate"), Permission.of("memory.*")}
    )
    return Agent(
        identity=identity,
        provider=provider,
        memory=memory,
        policy=policy,
        event_bus=events,
    )


def test_full_agent_run_with_memory_and_events(identity, events, memory):
    agent = build_agent(identity, events, memory)
    started = []
    stored = []
    events.subscribe(lambda e: started.append(e), EventType.AGENT_STARTED)
    events.subscribe(lambda e: stored.append(e), EventType.MEMORY_STORED)

    agent.start()
    assert agent.state is AgentState.RUNNING

    request = Request.create(
        source="owner", content="integration check", metadata={"trace": "t1"}
    )
    response = agent.process(request)

    assert response.status is ResponseStatus.OK
    assert response.agent_id == identity.agent_id
    assert memory.metadata()["stored"] == 1
    assert len(started) == 1
    assert len(stored) == 1
    assert stored[0].payload["key"] == f"request:{request.request_id}"

    agent.stop()
    assert agent.state is AgentState.STOPPED


def test_permission_denied_end_to_end(identity, events, memory):
    provider = MockProvider()
    policy = DefaultDenyPolicy()  # default deny
    agent = Agent(
        identity=identity,
        provider=provider,
        memory=memory,
        policy=policy,
        event_bus=events,
    )
    denied = []
    events.subscribe(lambda e: denied.append(e), EventType.PERMISSION_DENIED)

    agent.start()
    response = agent.process(Request.create(source="owner", content="blocked"))
    assert response.status is ResponseStatus.DENIED
    assert len(denied) == 1
    assert memory.metadata()["stored"] == 0


def test_handover_flow_end_to_end(identity, events):
    ownership = Ownership.create("kishir")
    handover = Handover(ownership=ownership, event_bus=events)
    types = []
    events.subscribe(lambda e: types.append(e.type))

    request = handover.request(target_owner="rishi", reason="handover to rishi")
    assert ownership.state is OwnershipState.TRANSFER_PENDING

    handover.approve(request, approver="kishir")
    new_ownership = handover.complete(request)

    assert new_ownership.current_owner == "rishi"
    assert ownership.state is OwnershipState.TRANSFERRED
    assert EventType.HANDOVER_REQUESTED in types
    assert EventType.HANDOVER_APPROVED in types
    assert EventType.HANDOVER_COMPLETED in types
    assert EventType.OWNERSHIP_CHANGED in types


def test_agent_connects_to_core_adapter(identity, events):
    agent = build_agent(identity, events, LocalMemory())
    agent.start()

    core = LocalCOREAdapter()
    assert core.connect(authorized=True)
    registered = core.register_agent(agent.identity)
    assert registered.ok

    health = core.report_health(
        {"agent_id": agent.identity.agent_id, "state": agent.state.value}
    )
    assert health.ok

    published = core.publish_event(
        agent._emit(EventType.AGENT_STARTED, agent_id=agent.identity.agent_id)
    )
    assert published.ok
    assert len(core.events_published) == 1


def test_agent_memory_syncs_to_rescs_adapter(identity, events):
    memory = LocalMemory()
    agent = build_agent(identity, events, memory)
    agent.start()
    agent.process(Request.create(source="owner", content="synced fact"))

    rescs = LocalRESCSAdapter()
    assert rescs.connect(authorized=True)
    record = memory.search("synced fact").records[0]
    put = rescs.put(record)
    assert put.ok
    got = rescs.get(record.record_id)
    assert got.payload["content"] == "synced fact"


def test_config_driven_agent_build(identity, events):
    from tiviss.configuration import TIVISSConfig

    config = TIVISSConfig.load(
        {
            "agent": {"name": "cfg-agent", "owner_id": "kishir", "agent_id": "cfg-id"},
            "permissions": {"allow": ["conversation.generate"]},
        }
    )
    cfg_identity = config.build_identity()
    agent = Agent(
        identity=cfg_identity,
        provider=config.build_provider(),
        policy=config.build_policy(),
        memory=config.build_memory(),
        event_bus=events,
    )
    agent.start()
    response = agent.process(Request.create(source="owner", content="from config"))
    assert response.status is ResponseStatus.OK
    assert response.agent_id == "cfg-id"


def test_rejected_handover_keeps_agent_runnable(identity, events, memory):
    ownership = Ownership.create("kishir")
    handover = Handover(ownership=ownership, event_bus=events)
    request = handover.request(target_owner="rishi")
    handover.reject(request, actor="owner", reason="changed my mind")
    assert ownership.state is OwnershipState.ACTIVE

    agent = Agent(
        identity=identity,
        provider=MockProvider(),
        memory=memory,
        policy=DefaultDenyPolicy(allow={Permission.of("conversation.generate")}),
        event_bus=events,
    )
    agent.start()
    response = agent.process(Request.create(source="owner", content="still working"))
    assert response.ok
