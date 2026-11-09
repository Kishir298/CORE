"""
Main A.S.I.S. runtime controller.
"""

from __future__ import annotations

from collections.abc import Iterable

from asis.logging.logger import get_logger

from .component import RuntimeComponent
from .context import RuntimeContext
from .interrupt import InterruptCoordinator
from .lifecycle import LifecycleManager
from .state import RuntimeState


class ASISRuntime:
    """Central lifecycle controller for A.S.I.S."""

    def __init__(
        self,
        components: Iterable[RuntimeComponent] | None = None,
    ) -> None:
        self.logger = get_logger("runtime")

        self.state = RuntimeState.CREATED

        self.context = RuntimeContext()
        self.lifecycle = LifecycleManager()
        self.interrupts = InterruptCoordinator()

        if components is not None:
            self.lifecycle.register_many(components)

    @property
    def is_running(self) -> bool:
        """Return whether the runtime is currently running."""
        return self.state == RuntimeState.RUNNING

    def register(self, component: RuntimeComponent) -> None:
        """Register a component."""
        if self.state not in {RuntimeState.CREATED, RuntimeState.STOPPED}:
            raise RuntimeError(
                "Components cannot be registered while the runtime is active."
            )

        self.lifecycle.register(component)

    def start(self) -> None:
        """Start the A.S.I.S. runtime."""
        if self.state == RuntimeState.RUNNING:
            return

        if self.state == RuntimeState.STARTING:
            raise RuntimeError("Runtime is already starting.")

        self.logger.info("Starting A.S.I.S. runtime.")
        self.state = RuntimeState.STARTING

        try:
            self.lifecycle.start_all(self.context)
            self.state = RuntimeState.RUNNING
            self.logger.info("A.S.I.S. runtime is running.")

        except Exception:
            self.state = RuntimeState.FAILED
            self.logger.exception("A.S.I.S. runtime startup failed.")
            raise

    def stop(self, timeout: float | None = None) -> None:
        """Stop the A.S.I.S. runtime, enforcing the shutdown timeout.

        Cooperative cancellation is requested first; component shutdown
        then runs bounded by ``timeout`` (defaults to
        ``settings.runtime.shutdown_timeout``). On expiry the runtime
        logs the responsible components, transitions to FAILED and
        raises ``TimeoutError`` instead of hanging forever.
        """
        if self.state in {RuntimeState.CREATED, RuntimeState.STOPPED}:
            return

        import threading
        import time

        from asis.configuration.settings import settings

        limit = settings.runtime.shutdown_timeout if timeout is None else timeout
        if limit is None or limit <= 0:
            limit = settings.runtime.shutdown_timeout

        self.logger.info("Stopping A.S.I.S. runtime.")
        self.state = RuntimeState.STOPPING

        self.interrupts.cancel_all()

        errors: list[BaseException] = []

        def _stop_components() -> None:
            try:
                self.lifecycle.stop_all(self.context)
            except Exception as exc:  # captured for the caller thread
                errors.append(exc)

        worker = threading.Thread(
            target=_stop_components, name="asis-shutdown", daemon=True
        )
        started = time.monotonic()
        worker.start()
        worker.join(timeout=limit)
        elapsed = time.monotonic() - started

        if worker.is_alive():
            names = self.lifecycle.list_components()
            self.logger.error(
                "Shutdown timeout after %.2fs (limit %.2fs); "
                "components may be stuck: %s",
                elapsed,
                float(limit),
                ", ".join(names) if names else "none",
            )
            self.state = RuntimeState.FAILED
            raise TimeoutError(
                f"Shutdown timed out after {limit:g}s; "
                f"stuck components: {', '.join(names) if names else 'unknown'}"
            )

        if errors:
            self.state = RuntimeState.FAILED
            self.logger.exception("A.S.I.S. runtime shutdown failed.")
            raise errors[0]

        try:
            self.context.clear()
        except Exception:
            self.state = RuntimeState.FAILED
            self.logger.exception("A.S.I.S. runtime shutdown failed.")
            raise

        self.state = RuntimeState.STOPPED
        self.logger.info("A.S.I.S. runtime stopped.")

    def restart(self) -> None:
        """Restart the A.S.I.S. runtime."""
        self.stop()
        self.start()

    def component_names(self) -> list[str]:
        """Return names of registered components."""
        return self.lifecycle.list_components()
