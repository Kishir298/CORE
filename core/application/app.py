from core.communication import LocalCommunication
from core.configuration import ConfigurationManager
from core.dependencies import DependencyManager
from core.events import EventBus
from core.health import HealthMonitor
from core.logging import CoreLogger
from core.organization import OrganizationEngine
from core.resources import ResourceRegistry
from core.routing import Router
from core.runtime import Runtime
from core.security import SecurityManager
from core.services import ServiceManager


class CoreApplication:
    """
    Top-level C.O.R.E. application.

    Owns and coordinates the major C.O.R.E. subsystems.
    """

    def __init__(self) -> None:
        self.runtime = Runtime()

        self.configuration = ConfigurationManager()
        self.logger = CoreLogger()

        self.communication = LocalCommunication()
        self.resources = ResourceRegistry()
        self.organization = OrganizationEngine()
        self.routing = Router(self.communication)
        self.events = EventBus()
        self.health = HealthMonitor()
        self.dependencies = DependencyManager()
        self.security = SecurityManager()
        self.services = ServiceManager()

        self._initialized = False

        self._register_runtime_components()
        self._initialized = True

    def _register_runtime_components(self) -> None:
        """
        Register application lifecycle hooks with the runtime.
        """

        self.runtime.register_component(
            "communication",
            self._initialize_communication,
            self._shutdown_communication,
        )

        self.runtime.register_component(
            "events",
            self._initialize_events,
            self._shutdown_events,
        )

    def _initialize_communication(self) -> None:
        """Initialize local communication."""
        pass

    def _shutdown_communication(self) -> None:
        """Shutdown local communication."""
        self.communication.clear()

    def _initialize_events(self) -> None:
        """Initialize the event system."""
        pass

    def _shutdown_events(self) -> None:
        """Shutdown the event system."""
        self.events.clear()

    def start(self) -> None:
        """Start C.O.R.E."""

        if not self._initialized:
            raise RuntimeError(
                "C.O.R.E. application is not initialized."
            )

        self.runtime.start()

    def stop(self) -> None:
        """Stop C.O.R.E."""

        self.runtime.stop()

    def restart(self) -> None:
        """Restart C.O.R.E."""

        self.runtime.restart()

    @property
    def state(self):
        """Return the current C.O.R.E. runtime state."""

        return self.runtime.state

    @property
    def is_running(self) -> bool:
        """Return whether C.O.R.E. is currently running."""

        return self.runtime.state.value == "running"
