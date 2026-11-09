"""
Runtime lifecycle management for A.S.I.S.
"""

from __future__ import annotations

from collections.abc import Iterable

from asis.logging.logger import get_logger

from .component import RuntimeComponent
from .context import RuntimeContext


class LifecycleManager:
    """Controls startup and shutdown of runtime components."""

    def __init__(self) -> None:
        self.logger = get_logger("runtime.lifecycle")
        self._components: list[RuntimeComponent] = []
        self._started: list[RuntimeComponent] = []

    def register(self, component: RuntimeComponent) -> None:
        """Register a component."""
        if any(existing.name == component.name for existing in self._components):
            raise ValueError(f"Runtime component already registered: {component.name}")

        self._components.append(component)

    def register_many(self, components: Iterable[RuntimeComponent]) -> None:
        """Register multiple components."""
        for component in components:
            self.register(component)

    def start_all(self, context: RuntimeContext) -> None:
        """Start components in registration order."""
        self._started.clear()

        try:
            for component in self._components:
                self.logger.info(
                    "Starting component: %s",
                    component.name,
                )

                component.start(context)
                self._started.append(component)

        except Exception:
            self.logger.exception("Component startup failed.")
            self.stop_all(context)
            raise

    def stop_all(self, context: RuntimeContext) -> None:
        """Stop started components in reverse order."""
        for component in reversed(self._started):
            try:
                self.logger.info(
                    "Stopping component: %s",
                    component.name,
                )

                component.stop(context)

            except Exception:
                self.logger.exception(
                    "Failed to stop component: %s",
                    component.name,
                )

        self._started.clear()

    def list_components(self) -> list[str]:
        """Return registered component names."""
        return [component.name for component in self._components]
