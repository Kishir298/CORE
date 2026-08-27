from collections.abc import Callable

from core.runtime.state import RuntimeState


class RuntimeError(Exception):
    """Base exception for C.O.R.E. runtime errors."""


class Runtime:
    """
    Controls the lifecycle of C.O.R.E.

    Runtime coordinates component startup, shutdown, failure handling,
    and the active runtime state.
    """

    def __init__(self) -> None:
        self._state = RuntimeState.STOPPED
        self._components: list[tuple[str, Callable[[], None]]] = []
        self._shutdown_handlers: list[tuple[str, Callable[[], None]]] = []
        self._initialized_components: list[str] = []
        self._error: Exception | None = None

    @property
    def state(self) -> RuntimeState:
        return self._state

    @property
    def error(self) -> Exception | None:
        return self._error

    @property
    def is_running(self) -> bool:
        return self._state == RuntimeState.RUNNING

    def register_component(
        self,
        name: str,
        initializer: Callable[[], None],
        shutdown: Callable[[], None] | None = None,
    ) -> None:
        """Register a component in the runtime lifecycle."""

        if self._state != RuntimeState.STOPPED:
            raise RuntimeError(
                "Components cannot be registered while runtime is active."
            )

        if any(component_name == name for component_name, _ in self._components):
            raise RuntimeError(f"Component already registered: {name}")

        self._components.append((name, initializer))

        if shutdown is not None:
            self._shutdown_handlers.append((name, shutdown))

    def start(self) -> None:
        """Initialize all registered components and enter RUNNING state."""

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
        self._initialized_components.clear()
        self._state = RuntimeState.STARTING

        try:
            self._state = RuntimeState.INITIALIZING

            for name, initializer in self._components:
                initializer()
                self._initialized_components.append(name)

            self._state = RuntimeState.RUNNING

        except Exception as exc:
            self._error = exc
            self._state = RuntimeState.FAILED
            self._shutdown_initialized_components()

            raise RuntimeError(
                "C.O.R.E. runtime failed during initialization."
            ) from exc

    def stop(self) -> None:
        """Stop the runtime and shut down initialized components."""

        if self._state == RuntimeState.STOPPED:
            return

        if self._state == RuntimeState.SHUTTING_DOWN:
            return

        self._state = RuntimeState.SHUTTING_DOWN

        try:
            self._shutdown_initialized_components()
        finally:
            self._initialized_components.clear()
            self._state = RuntimeState.STOPPED

    def restart(self) -> None:
        """Stop and start the runtime."""

        if self._state != RuntimeState.STOPPED:
            self.stop()

        self.start()

    def _shutdown_initialized_components(self) -> None:
        """Shut down only components that successfully initialized."""

        initialized = set(self._initialized_components)

        for name, shutdown in reversed(self._shutdown_handlers):
            if name not in initialized:
                continue

            try:
                shutdown()
            except Exception:
                continue

    def component_count(self) -> int:
        return len(self._components)

    def initialized_component_count(self) -> int:
        return len(self._initialized_components)

    def clear_components(self) -> None:
        """Remove all registered components while stopped."""

        if self._state != RuntimeState.STOPPED:
            raise RuntimeError(
                "Components cannot be cleared while runtime is active."
            )

        self._components.clear()
        self._shutdown_handlers.clear()
        self._initialized_components.clear()