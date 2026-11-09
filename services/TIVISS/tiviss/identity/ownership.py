"""Ownership model for T.I.V.I.S.S.

Ownership separate from identity: while the identity defines what the agent
is, ownership defines who controls it. Ownership supports a controlled
transition mechanism that rejects invalid transitions. Real-world ownership
transfer is not implemented here; only the state model and controlled
mechanism are.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from .identity import utcnow


class OwnershipState(StrEnum):
    """State of an ownership relationship."""

    ACTIVE = "active"
    TRANSFER_PENDING = "transfer_pending"
    TRANSFERRED = "transferred"
    REVOKED = "revoked"


class OwnershipTransitionError(ValueError):
    """Raised when an ownership transition is not allowed."""


@dataclass(frozen=True)
class OwnershipTransfer:
    """Record of a completed ownership transfer."""

    previous_owner: str
    new_owner: str
    transferred_at: datetime


# Allowed transitions for ownership state.
#
#   ACTIVE            -> TRANSFER_PENDING  (begin transfer)
#   ACTIVE            -> REVOKED           (owner revoked)
#   TRANSFER_PENDING  -> ACTIVE            (transfer cancelled)
#   TRANSFER_PENDING  -> TRANSFERRED       (transfer completed)
#   TRANSFER_PENDING  -> REVOKED           (revoked during transfer)
#
# TRANSFERRED and REVOKED are terminal states.
_ALLOWED_TRANSITIONS: dict[OwnershipState, frozenset[OwnershipState]] = {
    OwnershipState.ACTIVE: frozenset(
        {OwnershipState.TRANSFER_PENDING, OwnershipState.REVOKED}
    ),
    OwnershipState.TRANSFER_PENDING: frozenset(
        {OwnershipState.ACTIVE, OwnershipState.TRANSFERRED, OwnershipState.REVOKED}
    ),
    OwnershipState.TRANSFERRED: frozenset(),
    OwnershipState.REVOKED: frozenset(),
}


@dataclass
class Ownership:
    """Current ownership of the agent with controlled transitions.

    ``complete_transfer`` returns a fresh :class:`Ownership` for the new
    owner; the previous owner's record remains in ``history`` with
    state ``TRANSFERRED``.
    """

    owner_id: str
    state: OwnershipState = OwnershipState.ACTIVE
    pending_target: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    history: list[OwnershipTransfer] = field(default_factory=list)
    note: str = ""
    """Latest operator note (e.g. revocation reason); audit-only."""

    @classmethod
    def create(cls, owner_id: str) -> Ownership:
        """Start ownership for ``owner_id`` in the ACTIVE state."""
        if not (isinstance(owner_id, str) and owner_id.strip()):
            raise OwnershipTransitionError("owner_id must be a non-empty string")
        return cls(owner_id=owner_id)

    @property
    def current_owner(self) -> str | None:
        """The active owner, or None when not active."""
        return self.owner_id if self.state is OwnershipState.ACTIVE else None

    def _transition(self, new_state: OwnershipState, *, reason: str = "") -> None:
        if new_state not in _ALLOWED_TRANSITIONS[self.state]:
            raise OwnershipTransitionError(
                f"ownership transition {self.state.value} -> "
                f"{new_state.value} is not allowed"
            )
        self.state = new_state
        self.updated_at = utcnow()

    def begin_transfer(self, target_owner: str) -> None:
        """Start a pending transfer toward ``target_owner``."""
        if not (isinstance(target_owner, str) and target_owner.strip()):
            raise OwnershipTransitionError("target_owner must be a non-empty string")
        if target_owner == self.owner_id:
            raise OwnershipTransitionError(
                "target_owner must differ from the current owner"
            )
        if self.state is not OwnershipState.ACTIVE:
            raise OwnershipTransitionError(
                f"ownership transfer requires active ownership, got {self.state.value}"
            )
        self._transition(OwnershipState.TRANSFER_PENDING)
        self.pending_target = target_owner

    def cancel_transfer(self) -> None:
        """Cancel a pending transfer, returning to ACTIVE."""
        if self.pending_target is None:
            raise OwnershipTransitionError("no pending transfer to cancel")
        if self.state is not OwnershipState.TRANSFER_PENDING:
            raise OwnershipTransitionError(
                f"no pending transfer to cancel from state {self.state.value}"
            )
        self._transition(OwnershipState.ACTIVE)
        self.pending_target = None

    def revoke(self, *, reason: str = "") -> None:
        """Revoke the current or pending ownership (reason kept as a note)."""
        if self.state in (OwnershipState.TRANSFERRED, OwnershipState.REVOKED):
            raise OwnershipTransitionError(
                f"ownership is already in terminal state {self.state.value}"
            )
        self._transition(OwnershipState.REVOKED)
        self.pending_target = None
        self.note = reason

    def complete_transfer(self) -> Ownership:
        """Complete a pending transfer and return ownership for the new owner.

        The new owner becomes ACTIVE; this record is terminal (TRANSFERRED)
        and is appended to ``history``.
        """
        if self.pending_target is None:
            raise OwnershipTransitionError("no pending transfer to complete")
        if self.state is not OwnershipState.TRANSFER_PENDING:
            raise OwnershipTransitionError(
                f"no pending transfer to complete from state {self.state.value}"
            )
        target = self.pending_target
        completed_at = utcnow()
        self._transition(OwnershipState.TRANSFERRED)
        self.pending_target = None
        self.history.append(
            OwnershipTransfer(
                previous_owner=self.owner_id,
                new_owner=target,
                transferred_at=completed_at,
            )
        )
        return Ownership(
            owner_id=target,
            state=OwnershipState.ACTIVE,
            pending_target=None,
            created_at=completed_at,
            updated_at=completed_at,
            history=list(self.history),
        )
