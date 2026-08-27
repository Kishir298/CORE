from collections.abc import Callable

from core.runtime.state import RuntimeState


class RuntimeError(Exception):
    """Base exception for C.O.R.E. runtime errors."""


class Runtime:
    """
    Controls the lifecycle of C.O.R.E.

    Runtime is responsible for coordinating startup, initialization,
    running state, shutdown, and fatal runtime failures.
    """

    def __init__(self) -> None:
        self._state = RuntimeState.STOPPED
        self._components: list[tuple[str, Callable[[], None]]] = []
        self._shutdown_handlers: list[tuple[str, Callable[[], None]]] = []
        self._error: Exception | None = None

    @property
    def state(self) -> RuntimeState:
        return self._state

    @property
    def error(self) -> Exception | None:
        return self._error

    def register_component(
        self,
        name: str,
        initializer: Callable[[], None],
        shutdown: Callable[[], None] | None = None,
    ) -> None:
        """Register a component that participates in the runtime lifecycle."""

        self._components.append((name, initializer))

        if shutdown is not None:
            self._shutdown_handlers.append((name, shutdown))

    def start(self) -> None:
        """Start and initialize C.O.R.E."""

        if self._state == RuntimeState.RUNNING:
            return

        if self._state not in {
            RuntimeState.STOPPED,
            RuntimeState.FAILED,
        }:
            raise RuntimeError(
                f"Cannot start runtime from state: {self._state.value}"
            )

        self._error = None
        self._state = RuntimeState.STARTING

        try:
            self._state = RuntimeState.INITIALIZING

            for _, initializer in self._components:
                initializer()

            self._state = RuntimeState.RUNNING

        except Exception as exc:
            self._error = exc
            self._state = RuntimeState.FAILED

            self._shutdown_initialized_components()
            raise RuntimeError(
                "C.O.R.E. runtime failed during initialization."
            ) from exc

    def stop(self) -> None:
        """Stop C.O.R.E. cleanly."""

        if self._state == RuntimeState.STOPPED:
            return

        if self._state == RuntimeState.SHUTTING_DOWN:
            return

        self._state = RuntimeState.SHUTTING_DOWN

        try:
            self._shutdown_initialized_components()
        finally:
            self._state = RuntimeState.STOPPED

    def restart(self) -> None:
        """Restart C.O.R.E."""

        if self._state != RuntimeState.STOPPED:
            self.stop()

        self.start()

    def _shutdown_initialized_components(self) -> None:
        """Run shutdown handlers in reverse registration order."""

        for _, shutdown in reversed(self._shutdown_handlers):
            try:
                shutdown()
            except Exception:
                # Shutdown should continue even if one component fails.
                continue

    def component_count(self) -> int:
        return len(self._components)

    def clear_components(self) -> None:
        """Remove all registered lifecycle components."""

        if self._state != RuntimeState.STOPPED:
            raise RuntimeError(
                "Components cannot be cleared while runtime is active."
            )

        self._components.clear()
        self._shutdown_handlers.clear()
