import pytest

from tiviss.identity import Ownership, OwnershipState, OwnershipTransitionError


def test_ownership_creation_is_active():
    ownership = Ownership.create("kishir")
    assert ownership.owner_id == "kishir"
    assert ownership.state is OwnershipState.ACTIVE
    assert ownership.current_owner == "kishir"


def test_begin_transfer_moves_to_pending():
    ownership = Ownership.create("kishir")
    ownership.begin_transfer("rishi")
    assert ownership.state is OwnershipState.TRANSFER_PENDING
    assert ownership.pending_target == "rishi"
    assert ownership.current_owner is None


def test_cancel_transfer_returns_to_active():
    ownership = Ownership.create("kishir")
    ownership.begin_transfer("rishi")
    ownership.cancel_transfer()
    assert ownership.state is OwnershipState.ACTIVE
    assert ownership.pending_target is None
    assert ownership.current_owner == "kishir"


def test_complete_transfer_moves_ownership_to_new_owner():
    ownership = Ownership.create("kishir")
    ownership.begin_transfer("rishi")
    new_ownership = ownership.complete_transfer()

    assert ownership.state is OwnershipState.TRANSFERRED
    assert ownership.pending_target is None
    assert len(ownership.history) == 1
    assert ownership.history[0].previous_owner == "kishir"
    assert ownership.history[0].new_owner == "rishi"

    assert new_ownership.owner_id == "rishi"
    assert new_ownership.state is OwnershipState.ACTIVE
    assert new_ownership.current_owner == "rishi"


def test_revoke_from_active():
    ownership = Ownership.create("kishir")
    ownership.revoke()
    assert ownership.state is OwnershipState.REVOKED
    assert ownership.current_owner is None


def test_revoke_during_pending_transfer():
    ownership = Ownership.create("kishir")
    ownership.begin_transfer("rishi")
    ownership.revoke()
    assert ownership.state is OwnershipState.REVOKED
    assert ownership.pending_target is None


def test_invalid_transition_transfer_from_transferred():
    ownership = Ownership.create("kishir")
    ownership.begin_transfer("rishi")
    ownership.complete_transfer()
    with pytest.raises(OwnershipTransitionError):
        ownership.begin_transfer("still-rishi")


def test_invalid_transition_transfer_from_revoked():
    ownership = Ownership.create("kishir")
    ownership.revoke()
    with pytest.raises(OwnershipTransitionError):
        ownership.begin_transfer("rishi")


def test_invalid_transition_complete_without_pending_transfer():
    ownership = Ownership.create("kishir")
    with pytest.raises(OwnershipTransitionError):
        ownership.complete_transfer()


def test_invalid_transition_cancel_without_pending_transfer():
    ownership = Ownership.create("kishir")
    with pytest.raises(OwnershipTransitionError):
        ownership.cancel_transfer()


def test_transfer_to_same_owner_rejected():
    ownership = Ownership.create("kishir")
    with pytest.raises(OwnershipTransitionError):
        ownership.begin_transfer("kishir")


def test_transfer_to_empty_owner_rejected():
    ownership = Ownership.create("kishir")
    with pytest.raises(OwnershipTransitionError):
        ownership.begin_transfer("")


def test_revoke_is_terminal():
    ownership = Ownership.create("kishir")
    ownership.revoke()
    with pytest.raises(OwnershipTransitionError):
        ownership.revoke()
