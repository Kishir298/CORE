import pytest

from tiviss.events import EventBus, EventType
from tiviss.handover import (
    Handover,
    HandoverRequest,
    HandoverStage,
    HandoverTransitionError,
    HandoverValidationError,
)
from tiviss.identity import Ownership, OwnershipState


@pytest.fixture
def ownership():
    return Ownership.create("kishir")


@pytest.fixture
def bus():
    return EventBus()


def make_handover(ownership, bus):
    return Handover(ownership=ownership, event_bus=bus)


def test_request_creation_defaults():
    request = HandoverRequest.create(current_owner="kishir", target_owner="rishi")
    assert request.stage is HandoverStage.REQUESTED
    assert request.status is HandoverStage.REQUESTED
    assert request.validate() == []
    assert request.audit[0].action == "requested"


def test_request_same_owner_rejected():
    with pytest.raises(HandoverValidationError):
        HandoverRequest.create(current_owner="kishir", target_owner="kishir")


def test_request_empty_owner_rejected():
    with pytest.raises(HandoverValidationError):
        HandoverRequest.create(current_owner="", target_owner="rishi")


def test_request_validation_lists_problems():
    request = HandoverRequest.create(current_owner="kishir", target_owner="rishi")
    request.current_owner = ""
    problems = request.validate()
    assert "current_owner is required" in problems


def test_handover_request_flow(ownership, bus):
    manager = make_handover(ownership, bus)
    request = manager.request(target_owner="rishi", reason="transfer")
    assert request.stage is HandoverStage.REQUESTED

    manager.approve(request, approver="kishir")
    assert request.stage is HandoverStage.APPROVED
    assert request.approver == "kishir"

    new_ownership = manager.complete(request)
    assert request.stage is HandoverStage.COMPLETED
    assert new_ownership.current_owner == "rishi"
    assert ownership.state is OwnershipState.TRANSFERRED


def test_rejection(ownership, bus):
    manager = make_handover(ownership, bus)
    request = manager.request(target_owner="rishi")
    manager.reject(request, actor="owner", reason="not ready")
    assert request.stage is HandoverStage.REJECTED
    assert request.rejection_reason == "not ready"
    assert ownership.state is OwnershipState.ACTIVE


def test_cancellation(ownership, bus):
    manager = make_handover(ownership, bus)
    request = manager.request(target_owner="rishi")
    manager.cancel(request, actor="owner")
    assert request.stage is HandoverStage.CANCELLED
    assert ownership.state is OwnershipState.ACTIVE


def test_invalid_transition_approve_twice(ownership, bus):
    manager = make_handover(ownership, bus)
    request = manager.request(target_owner="rishi")
    manager.approve(request, approver="kishir")
    with pytest.raises(HandoverTransitionError):
        request.approve("kishir")


def test_invalid_transition_complete_without_approval(ownership, bus):
    manager = make_handover(ownership, bus)
    request = manager.request(target_owner="rishi")
    with pytest.raises(HandoverTransitionError):
        manager.complete(request)


def test_invalid_transition_reject_after_complete(ownership, bus):
    manager = make_handover(ownership, bus)
    request = manager.request(target_owner="rishi")
    manager.approve(request, approver="kishir")
    manager.complete(request)
    with pytest.raises(HandoverTransitionError):
        request.reject("owner")


def test_audit_events_emitted(ownership, bus):
    types = []
    bus.subscribe(lambda e: types.append(e.type))
    manager = make_handover(ownership, bus)
    request = manager.request(target_owner="rishi")
    manager.approve(request, approver="kishir")
    manager.complete(request)

    assert EventType.HANDOVER_REQUESTED in types
    assert EventType.HANDOVER_APPROVED in types
    assert EventType.HANDOVER_COMPLETED in types
    assert EventType.OWNERSHIP_CHANGED in types


def test_reject_emits_event(ownership, bus):
    received = []
    bus.subscribe(lambda e: received.append(e.type), EventType.HANDOVER_REJECTED)
    manager = make_handover(ownership, bus)
    request = manager.request(target_owner="rishi")
    manager.reject(request, reason="no")
    assert received == [EventType.HANDOVER_REJECTED]


def test_request_requires_active_ownership(bus):
    ownership = Ownership.create("kishir")
    ownership.begin_transfer("rishi")
    manager = make_handover(ownership, bus)
    with pytest.raises(HandoverValidationError):
        manager.request(target_owner="rishi")


def test_foreign_request_rejected(ownership, bus):
    manager = make_handover(ownership, bus)
    foreign = HandoverRequest.create(current_owner="someone-else", target_owner="rishi")
    with pytest.raises(HandoverValidationError):
        manager.approve(foreign, approver="kishir")


def test_history_records_audit(ownership, bus):
    manager = make_handover(ownership, bus)
    request = manager.request(target_owner="rishi")
    manager.approve(request, approver="kishir")
    manager.complete(request)
    history = manager.history()
    assert len(history) == 1
    assert history[0]["target_owner"] == "rishi"
    assert history[0]["stage"] == "completed"
    assert "requested" in history[0]["audit"]
    assert "approved" in history[0]["audit"]
    assert "completed" in history[0]["audit"]


def test_cancel_after_approval(ownership, bus):
    manager = make_handover(ownership, bus)
    request = manager.request(target_owner="rishi")
    manager.approve(request, approver="kishir")
    manager.cancel(request, actor="kishir")
    assert request.stage is HandoverStage.CANCELLED
    assert ownership.state is OwnershipState.ACTIVE
