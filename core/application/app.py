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
from core.services import ServiceManager, Service


class CoreApplication:
    """Top-level C.O.R.E. application."""

    def __init__(self) -> None:
        self.runtime = Runtime()

        self.configuration = ConfigurationManager()
        self.logger = CoreLogger()

        self.communication = LocalCommunication()
        self.resources = ResourceRegistry()
        self.organization = OrganizationEngine()
        self.events = EventBus()
        self.health = HealthMonitor()
        self.dependencies = DependencyManager()
        self.security = SecurityManager()
        self.services = ServiceManager()
        self.routing = Router(self.communication)

        self._initialized = False

        self._register_runtime_components()
        self._register_dependencies()
        self._register_internal_services()

        self._initialized = True

    def _register_runtime_components(self) -> None:
        self.runtime.register_component(
            "core",
            self._initialize,
            self._shutdown,
        )

    def _register_dependencies(self) -> None:
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
            "dependencies": [],
            "services": ["dependencies", "health"],
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

    def _register_internal_services(self) -> None:
        internal_services = [
            Service(
                service_id="communication",
                name="Communication",
                version="0.1.0",
                dependencies=["events", "security"],
            ),
            Service(
                service_id="events",
                name="Event System",
                version="0.1.0",
                dependencies=[],
            ),
            Service(
                service_id="resources",
                name="Resource Manager",
                version="0.1.0",
                dependencies=["configuration"],
            ),
            Service(
                service_id="organization",
                name="Organization Engine",
                version="0.1.0",
                dependencies=["resources"],
            ),
            Service(
                service_id="routing",
                name="Data Router",
                version="0.1.0",
                dependencies=["communication"],
            ),
            Service(
                service_id="health",
                name="Health Monitor",
                version="0.1.0",
                dependencies=["events"],
            ),
        ]

        for service in internal_services:
            self.services.register(service)

    def _initialize(self) -> None:
        self._register_health_checks()

        self.logger.info("C.O.R.E. initialized.")

        self.events.emit(
            event_type="SYSTEM_STARTED",
            source="core",
            payload={"state": "running"},
        )

    def _register_health_checks(self) -> None:
        checks = {
            "runtime": self._check_runtime,
            "communication": self._check_communication,
            "events": self._check_events,
            "resources": self._check_resources,
            "services": self._check_services,
        }

        for component_id, check in checks.items():
            self.health.register(component_id, check)

    def _check_runtime(self) -> HealthResult:
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
        return HealthResult(
            component_id="communication",
            status=HealthStatus.HEALTHY,
            message="Local communication subsystem is available.",
        )

    def _check_events(self) -> HealthResult:
        return HealthResult(
            component_id="events",
            status=HealthStatus.HEALTHY,
            message="Event bus is available.",
        )

    def _check_resources(self) -> HealthResult:
        return HealthResult(
            component_id="resources",
            status=HealthStatus.HEALTHY,
            message="Resource registry is available.",
        )

    def _check_services(self) -> HealthResult:
        return HealthResult(
            component_id="services",
            status=HealthStatus.HEALTHY,
            message="Service manager is available.",
        )

    def _shutdown(self) -> None:
        if self.events:
            self.events.emit(
                event_type="SYSTEM_STOPPING",
                source="core",
                payload={"state": "stopping"},
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
        if not self._initialized:
            raise RuntimeError(
                "C.O.R.E. application is not initialized."
            )

        self.runtime.start()

    def stop(self) -> None:
        self.runtime.stop()

    def restart(self) -> None:
        self.stop()

        self._register_dependencies()
        self._register_internal_services()

        self.runtime.start()

    def health_check(self):
        return self.health.check_all()

    @property
    def state(self):
        return self.runtime.state

    @property
    def is_running(self) -> bool:
        return self.runtime.is_running