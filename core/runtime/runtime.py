from collections.abc import Callable

from core.runtime.state import RuntimeState


class RuntimeError(Exception):
    """Base exception for C.O.R.E. runtime errors."""


class Runtime:
    """
    Controls the lifecycle of C.O.R.E.

    Runtime coordinates component startup, dependency-aware ordering,
    shutdown, failure handling, and active runtime state.
    """

    def __init__(self) -> None:
        self._state = RuntimeState.STOPPED

        self._components: dict[str, Callable[[], None]] = {}
        self._shutdown_handlers: dict[str, Callable[[], None]] = {}
        self._component_dependencies: dict[str, set[str]] = {}

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
        dependencies: list[str] | None = None,
    ) -> None:
        """
        Register a component in the runtime lifecycle.

        Dependencies must be registered components and will be initialized
        before the component that depends on them.
        """

        if self._state != RuntimeState.STOPPED:
            raise RuntimeError(
                "Components cannot be registered while runtime is active."
            )

        if name in self._components:
            raise RuntimeError(f"Component already registered: {name}")

        self._components[name] = initializer
        self._component_dependencies[name] = set(dependencies or [])

        if shutdown is not None:
            self._shutdown_handlers[name] = shutdown

    def set_dependencies(
        self,
        name: str,
        dependencies: list[str],
    ) -> None:
        """Set the dependencies for an already-registered component."""

        if self._state != RuntimeState.STOPPED:
            raise RuntimeError(
                "Dependencies cannot be changed while runtime is active."
            )

        if name not in self._components:
            raise RuntimeError(f"Component not registered: {name}")

        self._component_dependencies[name] = set(dependencies)

    def get_dependencies(self, name: str) -> list[str]:
        """Return the registered dependencies for a component."""

        if name not in self._components:
            raise RuntimeError(f"Component not registered: {name}")

        return sorted(self._component_dependencies[name])

    def get_start_order(self) -> list[str]:
        """
        Resolve the complete dependency-aware startup order.

        Dependencies always appear before the components that require them.
        """

        order: list[str] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visiting:
                raise RuntimeError(
                    f"Circular dependency detected involving: {name}"
                )

            if name in visited:
                return

            if name not in self._components:
                raise RuntimeError(
                    f"Missing dependency: {name}"
                )

            visiting.add(name)

            for dependency in sorted(
                self._component_dependencies.get(name, set())
            ):
                visit(dependency)

            visiting.remove(name)
            visited.add(name)
            order.append(name)

        for name in self._components:
            visit(name)

        return order

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

            start_order = self.get_start_order()

            for name in start_order:
                initializer = self._components[name]

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
        """Shut down initialized components in reverse startup order."""

        for name in reversed(self._initialized_components):
            shutdown = self._shutdown_handlers.get(name)

            if shutdown is None:
                continue

            try:
                shutdown()
            except Exception:
                continue

    def component_count(self) -> int:
        """Return the number of registered components."""

        return len(self._components)

    def initialized_component_count(self) -> int:
        """Return the number of currently initialized components."""

        return len(self._initialized_components)

    def clear_components(self) -> None:
        """Remove all registered components while stopped."""

        if self._state != RuntimeState.STOPPED:
            raise RuntimeError(
                "Components cannot be cleared while runtime is active."
            )

        self._components.clear()
        self._shutdown_handlers.clear()
        self._component_dependencies.clear()
        self._initialized_components.clear()