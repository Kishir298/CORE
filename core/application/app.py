from core.communication import LocalCommunication
from core.configuration import ConfigurationManager
from core.dependencies import DependencyManager
from core.events import EventBus
from core.health import HealthMonitor, HealthResult, HealthStatus
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
        self._register_dependencies()

        self._initialized = True

    def _register_runtime_components(self) -> None:
        """Register application lifecycle hooks with the runtime."""

        self.runtime.register_component(
            "core",
            self._initialize,
            self._shutdown,
        )

    def _register_dependencies(self) -> None:
        """Register C.O.R.E. subsystem dependencies."""

        dependencies = {
            "configuration": [],
            "logging": ["configuration"],
            "security": ["configuration"],
            "resources": ["configuration"],
            "organization": ["resources"],
            "events": ["configuration"],
            "communication": ["events", "security"],
            "routing": ["communication"],
            "health": ["events"],
            "services": ["dependencies", "health"],
            "dependencies": [],
        }

        for component_id, component_dependencies in dependencies.items():
            self.dependencies.register(
                component_id,
                component_dependencies,
            )

        self.dependencies.register(
            "core",
            list(dependencies.keys()),
        )

        self.dependencies.validate()

    def _initialize(self) -> None:
        """Initialize C.O.R.E. application state."""

        self._register_health_checks()

        self.logger.info("C.O.R.E. initialized.")

        self.events.emit(
            event_type="SYSTEM_STARTED",
            source="core",
            payload={
                "state": "running",
            },
        )

    def _register_health_checks(self) -> None:
        """Register health checks for core subsystems."""

        self.health.register(
            "runtime",
            self._check_runtime,
        )

        self.health.register(
            "communication",
            self._check_communication,
        )

        self.health.register(
            "events",
            self._check_events,
        )

        self.health.register(
            "resources",
            self._check_resources,
        )

        self.health.register(
            "services",
            self._check_services,
        )

    def _check_runtime(self) -> HealthResult:
        """Check whether the C.O.R.E. runtime is running."""

        healthy = self.runtime.state.value == "running"

        return HealthResult(
            component_id="runtime",
            status=(
                HealthStatus.HEALTHY
                if healthy
                else HealthStatus.UNHEALTHY
            ),
            message=(
                "Runtime is running."
                if healthy
                else "Runtime is not running."
            ),
        )

    def _check_communication(self) -> HealthResult:
        """Check the local communication subsystem."""

        return HealthResult(
            component_id="communication",
            status=HealthStatus.HEALTHY,
            message="Local communication subsystem is available.",
        )

    def _check_events(self) -> HealthResult:
        """Check the event subsystem."""

        return HealthResult(
            component_id="events",
            status=HealthStatus.HEALTHY,
            message="Event bus is available.",
        )

    def _check_resources(self) -> HealthResult:
        """Check the resource registry."""

        return HealthResult(
            component_id="resources",
            status=HealthStatus.HEALTHY,
            message="Resource registry is available.",
        )

    def _check_services(self) -> HealthResult:
        """Check the service manager."""

        return HealthResult(
            component_id="services",
            status=HealthStatus.HEALTHY,
            message="Service manager is available.",
        )

    def _shutdown(self) -> None:
        """Clean up application state."""

        self.events.emit(
            event_type="SYSTEM_STOPPING",
            source="core",
            payload={
                "state": "stopping",
            },
        )

        self.services.clear()
        self.routing.clear()
        self.health.clear()
        self.events.clear()
        self.resources.clear()
        self.organization.clear()
        self.dependencies.clear()
        self.security.clear()

        self.logger.info("C.O.R.E. shutdown complete.")

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

        self.stop()

        self._register_dependencies()

        self.runtime.start()

    def health_check(self):
        """Run all registered health checks."""

        return self.health.check_all()

    @property
    def state(self):
        """Return the current runtime state."""

        return self.runtime.state

    @property
    def is_running(self) -> bool:
        """Return whether C.O.R.E. is running."""

        return self.runtime.state.value == "running"