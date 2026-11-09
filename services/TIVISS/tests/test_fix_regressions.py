"""Regressions for audit fixes: config parsing, handover atomicity, wordlimit."""

import pytest

from tiviss.configuration import ConfigValidationError, TIVISSConfig
from tiviss.events import EventBus
from tiviss.handover import (
    Handover,
    HandoverRequest,
    HandoverStage,
    HandoverTransitionError,
    HandoverValidationError,
)
from tiviss.identity import Ownership, OwnershipState
from tiviss.models import MockProvider
from tiviss.models.provider import ProviderError


@pytest.fixture
def ownership():
    return Ownership.create("kishir")


@pytest.fixture
def bus():
    return EventBus()


# --- config bool parsing -------------------------------------------------


@pytest.mark.parametrize("raw", ["false", "False", "0", "no", "off", ""])
def test_load_string_false_is_false(raw):
    config = TIVISSConfig.load(
        {
            "runtime": {"enabled": raw},
            "core": {"enabled": raw},
            "rescs": {"enabled": raw},
        }
    )
    assert config.runtime.enabled is False
    assert config.core.enabled is False
    assert config.rescs.enabled is False


@pytest.mark.parametrize("raw", ["true", "True", "1", "yes", "on", True])
def test_load_string_true_is_true(raw):
    config = TIVISSConfig.load({"core": {"enabled": raw}})
    assert config.core.enabled is True


def test_load_provider_local_rejected_as_unimplemented():
    with pytest.raises(ConfigValidationError, match="provider_id"):
        TIVISSConfig.load({"model": {"provider_id": "local"}})


def test_to_dict_is_detached_snapshot():
    config = TIVISSConfig.defaults()
    snapshot = config.to_dict()
    snapshot["agent"]["name"] = "MUTATED"
    snapshot["model"]["model_id"] = "MUTATED"
    snapshot["permissions"]["allow"].append("x.y")
    assert config.agent.name == "tiviss"
    assert config.model.model_id == "tiviss-mock-1"
    assert config.permissions.allow == []


# --- handover atomicity --------------------------------------------------


def test_foreign_request_object_rejected(ownership, bus):
    manager = Handover(ownership=ownership, event_bus=bus)
    mine = manager.request(target_owner="rishi")
    foreign = HandoverRequest.create(current_owner="kishir", target_owner="rishi")
    assert foreign.request_id != mine.request_id
    with pytest.raises(HandoverValidationError, match="unknown handover"):
        manager.reject(foreign, actor="kishir")
    # Mine is untouched and still pending.
    assert mine.stage is HandoverStage.REQUESTED
    assert ownership.state is OwnershipState.TRANSFER_PENDING


def test_double_reject_leaves_states_consistent(ownership, bus):
    manager = Handover(ownership=ownership, event_bus=bus)
    request = manager.request(target_owner="rishi")
    manager.reject(request, actor="kishir")
    assert request.stage is HandoverStage.REJECTED
    with pytest.raises(HandoverValidationError):
        manager.reject(request, actor="kishir")
    # Ownership returned to active exactly once; no divergence.
    assert ownership.state is OwnershipState.ACTIVE
    assert request.stage is HandoverStage.REJECTED


def test_complete_without_approval_keeps_pending(ownership, bus):
    manager = Handover(ownership=ownership, event_bus=bus)
    request = manager.request(target_owner="rishi")
    with pytest.raises(HandoverTransitionError):
        manager.complete(request)
    assert request.stage is HandoverStage.REQUESTED
    assert ownership.state is OwnershipState.TRANSFER_PENDING


# --- mock wordlimit ------------------------------------------------------


def test_wordlimit_rejects_non_integer_types():
    provider = MockProvider()
    for bad in (None, ["3"], {"n": 3}, 2.5, True):
        with pytest.raises(ProviderError, match="wordlimit"):
            provider.generate("one two three four", context={"wordlimit": bad})


def test_wordlimit_rejects_negative():
    provider = MockProvider()
    with pytest.raises(ProviderError, match="wordlimit"):
        provider.generate("one two three", context={"wordlimit": -1})


def test_wordlimit_zero_and_string_ok():
    provider = MockProvider()
    assert provider.generate("one two", context={"wordlimit": 0}).content.endswith(
        ": "
    )
    resp = provider.generate("one two three", context={"wordlimit": "2"})
    assert resp.content.endswith("one two")
