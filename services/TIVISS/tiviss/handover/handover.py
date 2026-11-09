"""Controlled handover subsystem.

A handover moves agent ownership from one person to another through a
validated, auditable pipeline:

    Request -> Validation -> Approval -> Completion -> New Owner

This version implements the data models, state transitions, validation, and
audit events. Real-world transfer mechanics are intentionally NOT
implemented; ownership changes are driven through :class:`Ownership`.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..events.events import Event, EventBus, EventType
from ..identity.identity import utcnow
from ..identity.ownership import Ownership, OwnershipState, OwnershipTransitionError
from .state import (
    HandoverStage,
    HandoverTransitionError,
    assert_valid_handover_transition,
)


class HandoverValidationError(ValueError):
    """Raised when a handover request is invalid."""


@dataclass(frozen=True)
class HandoverAuditEntry:
    """An auditable action within a handover."""

    actor: str
    action: str
    timestamp: datetime
    detail: str = ""


@dataclass
class HandoverRequest:
    """A single handover request with its own validated state machine."""

    request_id: str
    current_owner: str
    target_owner: str
    reason: str
    stage: HandoverStage
    created_at: datetime
    updated_at: datetime
    audit: list[HandoverAuditEntry] = field(default_factory=list)
    approver: str | None = None
    rejection_reason: str = ""
    completed_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        current_owner: str,
        target_owner: str,
        reason: str = "",
        request_id: str | None = None,
        actor: str = "system",
    ) -> HandoverRequest:
        errors: list[str] = []
        if not (isinstance(current_owner, str) and current_owner.strip()):
            errors.append("current_owner must be a non-empty string")
        if not (isinstance(target_owner, str) and target_owner.strip()):
            errors.append("target_owner must be a non-empty string")
        if target_owner == current_owner:
            errors.append("target_owner must differ from current_owner")
        if errors:
            raise HandoverValidationError("; ".join(errors))

        now = utcnow()
        request = cls(
            request_id=request_id or str(uuid.uuid4()),
            current_owner=current_owner,
            target_owner=target_owner,
            reason=reason,
            stage=HandoverStage.REQUESTED,
            created_at=now,
            updated_at=now,
        )
        request._audit(actor, "requested", reason)
        return request

    @property
    def status(self) -> HandoverStage:
        return self.stage

    def _audit(self, actor: str, action: str, detail: str = "") -> None:
        self.audit.append(
            HandoverAuditEntry(
                actor=actor, action=action, timestamp=utcnow(), detail=detail
            )
        )

    def _transition(self, target: HandoverStage) -> None:
        assert_valid_handover_transition(self.stage, target)
        self.stage = target
        self.updated_at = utcnow()

    def approve(self, approver: str) -> None:
        if not (isinstance(approver, str) and approver.strip()):
            raise HandoverValidationError("approver must be a non-empty string")
        # N14: only the current owner may approve a handover.
        if approver.strip() != self.current_owner:
            raise HandoverValidationError(
                "approver must be the current owner of the handover request"
            )
        self._transition(HandoverStage.APPROVED)
        self.approver = approver
        self._audit(approver, "approved")

    def reject(self, actor: str, *, reason: str = "") -> None:
        if not (isinstance(actor, str) and actor.strip()):
            raise HandoverValidationError("actor must be a non-empty string")
        self._transition(HandoverStage.REJECTED)
        self.rejection_reason = reason
        self._audit(actor, "rejected", reason)

    def cancel(self, actor: str, *, reason: str = "") -> None:
        if not (isinstance(actor, str) and actor.strip()):
            raise HandoverValidationError("actor must be a non-empty string")
        self._transition(HandoverStage.CANCELLED)
        self._audit(actor, "cancelled", reason)

    def complete(self, actor: str) -> None:
        if not (isinstance(actor, str) and actor.strip()):
            raise HandoverValidationError("actor must be a non-empty string")
        self._transition(HandoverStage.COMPLETED)
        self.completed_at = utcnow()
        self._audit(actor, "completed")

    def validate(self) -> list[str]:
        """Independent validation; returns a list of problems (empty when valid)."""
        errors: list[str] = []
        if not (isinstance(self.request_id, str) and self.request_id.strip()):
            errors.append("request_id is required")
        if not (isinstance(self.current_owner, str) and self.current_owner.strip()):
            errors.append("current_owner is required")
        if not (isinstance(self.target_owner, str) and self.target_owner.strip()):
            errors.append("target_owner is required")
        if self.current_owner == self.target_owner:
            errors.append("target_owner must differ from current_owner")
        return errors


class Handover:
    """Coordinates a handover between :class:`Ownership` and event emission."""

    def __init__(
        self, *, ownership: Ownership, event_bus: EventBus | None = None
    ) -> None:
        self._ownership = ownership
        self.events = event_bus or EventBus()
        self.requests: dict[str, HandoverRequest] = {}

    @property
    def ownership(self) -> Ownership:
        return self._ownership

    def request(
        self, *, target_owner: str, reason: str = "", actor: str = "system"
    ) -> HandoverRequest:
        """Validate ownership, create a request, and open a pending transfer."""
        if self._ownership.current_owner is None:
            raise HandoverValidationError(
                f"handover requires an active owner; ownership is "
                f"{self._ownership.state.value}"
            )
        handover = HandoverRequest.create(
            current_owner=self._ownership.owner_id,
            target_owner=target_owner,
            reason=reason,
            actor=actor,
        )
        problems = handover.validate()
        if problems:
            raise HandoverValidationError("; ".join(problems))

        # Atomic: insert the request BEFORE mutating ownership so a failure
        # in begin_transfer never leaves ownership TRANSFER_PENDING with no
        # tracked request. Roll back the insert on any failure.
        self.requests[handover.request_id] = handover
        try:
            self._ownership.begin_transfer(target_owner)
        except OwnershipTransitionError as exc:
            self.requests.pop(handover.request_id, None)
            raise HandoverValidationError(str(exc)) from exc
        except Exception:
            self.requests.pop(handover.request_id, None)
            raise

        try:
            self.events.publish(
                Event.create(
                    type=EventType.HANDOVER_REQUESTED,
                    source="handover",
                    payload={
                        "request_id": handover.request_id,
                        "current_owner": handover.current_owner,
                        "target_owner": handover.target_owner,
                    },
                )
            )
        except Exception:
            # Roll back both sides if event emission fails.
            from contextlib import suppress as _suppress

            with _suppress(Exception):
                self._ownership.cancel_transfer()
            self.requests.pop(handover.request_id, None)
            raise
        return handover

    def _require_current_request(self, handover: HandoverRequest) -> None:
        if (
            handover.request_id not in self.requests
            or self.requests[handover.request_id] is not handover
        ):
            raise HandoverValidationError("unknown handover request")
        if handover.current_owner != self._ownership.owner_id:
            raise HandoverValidationError(
                "handover request does not belong to the current owner"
            )
        if self._ownership.state is not OwnershipState.TRANSFER_PENDING:
            raise HandoverValidationError(
                "ownership must be transfer_pending for an active handover, got "
                f"{self._ownership.state.value}"
            )
        if self._ownership.pending_target is None:
            raise HandoverValidationError(
                "ownership has no pending transfer target for this handover"
            )
        if handover.target_owner != self._ownership.pending_target:
            raise HandoverValidationError(
                "handover target does not match the pending ownership transfer"
            )

    @staticmethod
    def _precheck_transition(handover: HandoverRequest, target: HandoverStage) -> None:
        """Dry-run the request transition so paired ownership/request updates
        stay atomic: both transitions are pure in-memory state changes, so
        validating both preconditions before mutating either leaves no
        divergence window."""
        assert_valid_handover_transition(handover.stage, target)

    def approve(self, handover: HandoverRequest, *, approver: str) -> None:
        self._require_current_request(handover)
        if not (isinstance(approver, str) and approver.strip()):
            raise HandoverValidationError("approver must be a non-empty string")
        # N14: only the current owner may approve; prevents a target (or
        # third party) from self-approving a transfer.
        if approver.strip() != handover.current_owner:
            raise HandoverValidationError(
                "approver must be the current owner of the handover request"
            )
        handover.approve(approver)
        self.events.publish(
            Event.create(
                type=EventType.HANDOVER_APPROVED,
                source="handover",
                payload={"request_id": handover.request_id, "approver": approver},
            )
        )

    def reject(
        self, handover: HandoverRequest, *, actor: str = "owner", reason: str = ""
    ) -> None:
        if not (isinstance(actor, str) and actor.strip()):
            raise HandoverValidationError("actor must be a non-empty string")
        self._require_current_request(handover)
        self._precheck_transition(handover, HandoverStage.REJECTED)
        self._ownership.cancel_transfer()
        handover.reject(actor, reason=reason)
        self.events.publish(
            Event.create(
                type=EventType.HANDOVER_REJECTED,
                source="handover",
                payload={"request_id": handover.request_id, "reason": reason},
            )
        )

    def cancel(
        self, handover: HandoverRequest, *, actor: str = "owner", reason: str = ""
    ) -> None:
        if not (isinstance(actor, str) and actor.strip()):
            raise HandoverValidationError("actor must be a non-empty string")
        self._require_current_request(handover)
        self._precheck_transition(handover, HandoverStage.CANCELLED)
        self._ownership.cancel_transfer()
        handover.cancel(actor, reason=reason)
        self.events.publish(
            Event.create(
                type=EventType.HANDOVER_CANCELLED,
                source="handover",
                payload={"request_id": handover.request_id, "reason": reason},
            )
        )

    def complete(
        self, handover: HandoverRequest, *, actor: str = "system"
    ) -> Ownership:
        """Approve-required completion: transfers ownership to the target."""
        if not (isinstance(actor, str) and actor.strip()):
            raise HandoverValidationError("actor must be a non-empty string")
        if handover.stage is not HandoverStage.APPROVED:
            raise HandoverTransitionError(handover.stage, HandoverStage.COMPLETED)

        self._require_current_request(handover)
        self._precheck_transition(handover, HandoverStage.COMPLETED)
        new_ownership = self._ownership.complete_transfer()
        handover.complete(actor)
        self.events.publish(
            Event.create(
                type=EventType.HANDOVER_COMPLETED,
                source="handover",
                payload={
                    "request_id": handover.request_id,
                    "new_owner": new_ownership.owner_id,
                },
            )
        )
        self.events.publish(
            Event.create(
                type=EventType.OWNERSHIP_CHANGED,
                source="handover",
                payload={
                    "previous_owner": handover.current_owner,
                    "new_owner": new_ownership.owner_id,
                },
            )
        )
        self._ownership = new_ownership
        return new_ownership

    def history(self) -> tuple[Mapping[str, Any], ...]:
        """Audit trail of all requests seen by this handover manager."""
        return tuple(
            {
                "request_id": request.request_id,
                "current_owner": request.current_owner,
                "target_owner": request.target_owner,
                "stage": request.stage.value,
                "audit": [entry.action for entry in request.audit],
            }
            for request in self.requests.values()
        )
