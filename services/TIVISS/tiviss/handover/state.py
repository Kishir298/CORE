"""Handover state machine definitions."""

from __future__ import annotations

from enum import StrEnum


class HandoverStage(StrEnum):
    """Stages of a handover request.

    REQUESTED -> APPROVED  -> COMPLETED
    REQUESTED -> REJECTED  (terminal)
    REQUESTED -> CANCELLED (terminal)
    APPROVED  -> CANCELLED (terminal)
    """

    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# Convenience alias: the request status mirrors its stage.
HandoverRequestStatus = HandoverStage


class HandoverTransitionError(ValueError):
    """Raised when a handover state transition is not allowed."""

    def __init__(
        self,
        source: HandoverStage,
        target: HandoverStage,
        *,
        message: str | None = None,
    ) -> None:
        self.source = source
        self.target = target
        super().__init__(
            message
            or f"handover transition {source.value} -> {target.value} is not allowed"
        )


_ALLOWED_TRANSITIONS: dict[HandoverStage, frozenset[HandoverStage]] = {
    HandoverStage.REQUESTED: frozenset(
        {HandoverStage.APPROVED, HandoverStage.REJECTED, HandoverStage.CANCELLED}
    ),
    HandoverStage.APPROVED: frozenset(
        {HandoverStage.COMPLETED, HandoverStage.CANCELLED}
    ),
    HandoverStage.REJECTED: frozenset(),
    HandoverStage.COMPLETED: frozenset(),
    HandoverStage.CANCELLED: frozenset(),
}


def assert_valid_handover_transition(
    source: HandoverStage, target: HandoverStage
) -> None:
    if target not in _ALLOWED_TRANSITIONS[source]:
        raise HandoverTransitionError(source, target)
