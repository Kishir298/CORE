"""Timeout support: provider.generate + agent.process (offline)."""

import math

import pytest

from tiviss.agent import Agent
from tiviss.conversation import Request, ResponseStatus
from tiviss.identity import AgentIdentity
from tiviss.models import MockProvider
from tiviss.models.provider import ModelProvider, ProviderError
from tiviss.permissions import DefaultDenyPolicy, Permission


@pytest.fixture
def identity():
    return AgentIdentity.create(
        agent_id="tiviss-timeout", name="tiviss", version="0.1.0", owner_id="kishir"
    )


@pytest.fixture
def policy():
    return DefaultDenyPolicy(allow={Permission.of("conversation.generate")})


def make_agent(identity, policy, provider=None):
    return Agent(
        identity=identity, provider=provider or MockProvider(), policy=policy
    )


class RecordingProvider(MockProvider):
    """Mock that records the timeout it was called with."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.seen_timeouts: list = []

    def generate(self, content, *, context=None, timeout_s=None):
        self.seen_timeouts.append(timeout_s)
        return super().generate(content, context=context, timeout_s=timeout_s)


# --- provider.generate ----------------------------------------------------


def test_generate_default_none_ok():
    provider = MockProvider()
    resp = provider.generate("hello")
    assert resp.content == "ack(tiviss-mock-1): hello"


@pytest.mark.parametrize("timeout", [1, 2.5, 0.001, 30, 60.0])
def test_generate_accepts_positive_timeout(timeout):
    provider = MockProvider()
    resp = provider.generate("hello", timeout_s=timeout)
    assert "hello" in resp.content


@pytest.mark.parametrize("timeout", [0, 0.0, -1, -0.5, -100, -0.001])
def test_generate_rejects_zero_and_negative(timeout):
    provider = MockProvider()
    with pytest.raises(ProviderError, match="timeout_s"):
        provider.generate("hello", timeout_s=timeout)


@pytest.mark.parametrize(
    "timeout", ["1", True, False, [1], {"s": 1}, object(), float("nan")]
)
def test_generate_rejects_invalid_types(timeout):
    provider = MockProvider()
    with pytest.raises(ProviderError, match="timeout_s"):
        provider.generate("hello", timeout_s=timeout)


def test_generate_rejects_infinite_timeout():
    provider = MockProvider()
    with pytest.raises(ProviderError, match="timeout_s"):
        provider.generate("hello", timeout_s=math.inf)
    with pytest.raises(ProviderError, match="timeout_s"):
        provider.generate("hello", timeout_s=-math.inf)


def test_generate_timeout_does_not_mask_other_errors():
    provider = MockProvider(failure_mode=True)
    with pytest.raises(ProviderError):
        provider.generate("hello", timeout_s=5)
    provider = MockProvider()
    with pytest.raises(ProviderError):
        provider.generate("   ", timeout_s=5)


def test_abstract_signature_accepts_timeout():
    import inspect

    sig = inspect.signature(ModelProvider.generate)
    assert "timeout_s" in sig.parameters
    param = sig.parameters["timeout_s"]
    assert param.default is None


# --- agent.process --------------------------------------------------------


def test_process_default_no_timeout_ok(identity, policy):
    agent = make_agent(identity, policy)
    agent.start()
    resp = agent.process(Request.create(source="owner", content="ping"))
    assert resp.status is ResponseStatus.OK


@pytest.mark.parametrize("timeout", [1, 2.5, 5.0])
def test_process_accepts_positive_timeout(identity, policy, timeout):
    agent = make_agent(identity, policy)
    agent.start()
    resp = agent.process(
        Request.create(source="owner", content="ping"), timeout_s=timeout
    )
    assert resp.status is ResponseStatus.OK
    assert "ping" in resp.content


@pytest.mark.parametrize("timeout", [0, -1, -2.5, 0.0])
def test_process_invalid_timeout_returns_failed(identity, policy, timeout):
    agent = make_agent(identity, policy)
    agent.start()
    resp = agent.process(
        Request.create(source="owner", content="ping"), timeout_s=timeout
    )
    assert resp.status is ResponseStatus.FAILED
    assert resp.metadata.get("reason") == "provider_error"
    assert agent.requests_handled == 0


@pytest.mark.parametrize("timeout", ["bad", True, False, [1]])
def test_process_invalid_type_timeout_returns_failed(identity, policy, timeout):
    agent = make_agent(identity, policy)
    agent.start()
    resp = agent.process(
        Request.create(source="owner", content="ping"), timeout_s=timeout
    )
    assert resp.status is ResponseStatus.FAILED


def test_process_passes_timeout_to_provider(identity, policy):
    provider = RecordingProvider()
    agent = make_agent(identity, policy, provider=provider)
    agent.start()
    agent.process(Request.create(source="owner", content="hi"), timeout_s=7.5)
    assert provider.seen_timeouts == [7.5]
    agent.process(Request.create(source="owner", content="hi2"))
    assert provider.seen_timeouts == [7.5, None]
