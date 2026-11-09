"""Agent lifecycle state definitions and validated transitions."""

from __future__ import annotations

from enum import StrEnum


class AgentState(StrEnum):
    """States of the T.I.V.I.S.S. agent runtime."""

    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"


class LifecycleTransitionError(ValueError):
    """Raised when a lifecycle transition is not allowed."""

    def __init__(
        self, source: AgentState, target: AgentState, *, message: str | None = None
    ) -> None:
        self.source = source
        self.target = target
        super().__init__(
            message
            or f"lifecycle transition {source.value} -> {target.value} is not allowed"
        )


# Allowed lifecycle transitions.
#
#   CREATED   -> READY     (initialize)
#   READY     -> RUNNING   (start)
#   READY     -> STOPPING  (stop before first run)
#   RUNNING   -> READY     (idle / pause)
#   RUNNING   -> STOPPING  (stop)
#   STOPPING  -> STOPPED   (fully stopped)
#
# STOPPED is a terminal state.
TRANSITIONS: dict[AgentState, frozenset[AgentState]] = {
    AgentState.CREATED: frozenset({AgentState.READY}),
    AgentState.READY: frozenset({AgentState.RUNNING, AgentState.STOPPING}),
    AgentState.RUNNING: frozenset({AgentState.READY, AgentState.STOPPING}),
    AgentState.STOPPING: frozenset({AgentState.STOPPED}),
    AgentState.STOPPED: frozenset(),
}


def is_valid_transition(source: AgentState | str, target: AgentState | str) -> bool:
    source_state = AgentState(source)
    target_state = AgentState(target)
    return target_state in TRANSITIONS[source_state]


def assert_valid_transition(source: AgentState | str, target: AgentState | str) -> None:
    source_state = AgentState(source)
    target_state = AgentState(target)
    if not is_valid_transition(source_state, target_state):
        raise LifecycleTransitionError(source_state, target_state)
