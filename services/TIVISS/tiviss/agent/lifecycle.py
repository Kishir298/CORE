"""Lifecycle manager: a validated state machine over :class:`AgentState`."""

from __future__ import annotations

from collections.abc import Callable

from .state import AgentState, LifecycleTransitionError, assert_valid_transition

TransitionHook = Callable[[AgentState, AgentState], None]


class LifecycleManager:
    """Owns the agent state and enforces valid transitions.

    ``on_transition`` (when provided) is called AFTER a transition succeeds.
    A failing hook does not roll back the transition but is surfaced to the
    caller.
    """

    def __init__(self, *, on_transition: TransitionHook | None = None) -> None:
        self._state = AgentState.CREATED
        self._on_transition = on_transition

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state is AgentState.RUNNING

    def transition(self, target: AgentState | str) -> AgentState:
        """Validate and perform a transition. Raises on invalid moves."""
        target_state = AgentState(target)
        assert_valid_transition(self._state, target_state)
        previous = self._state
        self._state = target_state
        if self._on_transition is not None:
            self._on_transition(previous, self._state)
        return self._state

    def ensure(self, *states: AgentState | str) -> bool:
        """True when the current state is one of ``states``."""
        wanted = {AgentState(state) for state in states}
        return self._state in wanted

    def require(self, *states: AgentState | str) -> None:
        """Raise :class:`LifecycleTransitionError` when not in one of ``states``."""
        if not self.ensure(*states):
            wanted = "/".join(AgentState(state).value for state in states)
            raise LifecycleTransitionError(
                self._state, self._state, message=f"agent must be in one of: {wanted}"
            ) from None

    def reset(self) -> None:
        """Reset to CREATED (only meaningful before first run or after stop)."""
        if self._state is AgentState.STOPPED:
            self._state = AgentState.CREATED
            return
        raise LifecycleTransitionError(self._state, AgentState.CREATED)
