from pathlib import Path

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

SYSTEM_STARTED = "SYSTEM_STARTED"
SYSTEM_STOPPED = "SYSTEM_STOPPED"

DEFAULT_CONFIG_PATH = Path("config/core.yaml")

DEFAULT_RUNTIME_COMPONENTS = {
    "configuration": True,
    "logging": True,
    "security": True,
    "resources": True,
    "organization": True,
    "events": True,
    "communication": True,
    "routing": True,
    "health": True,
    "dependencies": True,
    "services": True,
    "core": True,
}


class CoreApplication:
    """
    Top-level C.O.R.E. application.

    CoreApplication owns the canonical runtime component graph and
    orchestrates genuine startup and shutdown of every C.O.R.E. subsystem.
    Startup initializes and activates components in dependency order and
    shutdown deactivates them in reverse order.
    """

    def __init__(
        self,
        config_path: str | Path | None = None,
        environment: str = "development",
    ) -> None:
        self._config_path = config_path
        self._environment = environment

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

    def _resolve_config_path(self) -> Path | None:
        """Resolve the configuration file to load, if any."""

        if self._config_path is not None:
            return Path(self._config_path)

        default = DEFAULT_CONFIG_PATH

        if default.exists():
            return default

        return None

    def _register_runtime_components(self) -> None:
        """
        Register all C.O.R.E. subsystems with the runtime.

        Runtime dependencies mirror the dependency graph maintained by
        DependencyManager so lifecycle orchestration follows the same
        architecture used by the rest of the application.
        """

        self.runtime.register_component(
            "configuration",
            self._initialize_configuration,
            self._shutdown_configuration,
        )

        self.runtime.register_component(
            "logging",
            self._initialize_logging,
            self._shutdown_logging,
            dependencies=["configuration"],
        )

        self.runtime.register_component(
            "security",
            self._initialize_security,
            self._shutdown_security,
            dependencies=["configuration"],
        )

        self.runtime.register_component(
            "resources",
            self._initialize_resources,
            self._shutdown_resources,
            dependencies=["configuration"],
        )

        self.runtime.register_component(
            "organization",
            self._initialize_organization,
            self._shutdown_organization,
            dependencies=["resources"],
        )

        self.runtime.register_component(
            "events",
            self._initialize_events,
            self._shutdown_events,
            dependencies=["configuration"],
        )

        self.runtime.register_component(
            "communication",
            self._initialize_communication,
            self._shutdown_communication,
            dependencies=["events", "security"],
        )

        self.runtime.register_component(
            "routing",
            self._initialize_routing,
            self._shutdown_routing,
            dependencies=["communication"],
        )

        self.runtime.register_component(
            "health",
            self._initialize_health,
            self._shutdown_health,
            dependencies=["events"],
        )

        self.runtime.register_component(
            "dependencies",
            self._initialize_dependencies,
            self._shutdown_dependencies,
        )

        self.runtime.register_component(
            "services",
            self._initialize_services,
            self._shutdown_services,
            dependencies=["dependencies", "health"],
        )

        self.runtime.register_component(
            "core",
            self._initialize,
            self._shutdown,
            dependencies=[
                "configuration",
                "logging",
                "security",
                "resources",
                "organization",
                "events",
                "communication",
                "routing",
                "health",
                "dependencies",
                "services",
            ],
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
            ),
            Service(
                service_id="events",
                name="Event System",
                version="0.1.0",
            ),
            Service(
                service_id="resources",
                name="Resource Manager",
                version="0.1.0",
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

    def _initialize_configuration(self) -> None:
        """Load and validate the C.O.R.E. configuration."""

        self.configuration.start()

        path = self._resolve_config_path()

        if path is None:
            self.logger.info(
                "No configuration file found; using defaults."
            )
            return

        self.configuration.load(path, environment=self._environment)

        self.logger.info(
            f"Configuration loaded: {path}"
        )

    def _initialize_logging(self) -> None:
        """Apply configuration-controlled logging behavior."""

        if not self.configuration.is_running:
            return

        if not self.configuration.has("logging.level"):
            return

        level = self.configuration.get("logging.level")

        mapping = {
            "DEBUG": 10,
            "INFO": 20,
            "WARNING": 30,
            "ERROR": 40,
            "CRITICAL": 50,
        }

        resolved = mapping.get(str(level).upper())

        if resolved is None:
            self.logger.warning(
                f"Unknown logging level: {level}"
            )
            return

        self.logger.set_level(resolved)

    def _initialize_security(self) -> None:
        """Activate the security infrastructure."""

        self.security.start()

    def _initialize_resources(self) -> None:
        """Activate the resource infrastructure."""

    def _initialize_organization(self) -> None:
        """Activate the organization infrastructure."""

    def _initialize_events(self) -> None:
        """Activate the event subsystem."""

        self.events.start()

    def _initialize_communication(self) -> None:
        """Activate the communication subsystem."""

        self.communication.start()

    def _initialize_routing(self) -> None:
        """Activate the routing subsystem."""

        self.routing.start()

    def _initialize_health(self) -> None:
        """Activate health monitoring and register component checks."""

        self.health.start()
        self._register_health_checks()

    def _initialize_dependencies(self) -> None:
        """Mark the dependency registry as active."""

        self.dependencies.validate()

    def _initialize_services(self) -> None:
        """Start C.O.R.E. internal services."""

        for service in self.services.list():
            try:
                self.services.start(service.service_id)
            except Exception as exc:
                self.logger.error(
                    f"Failed to start internal service "
                    f"'{service.service_id}': {exc}"
                )
                raise

    def _initialize(self) -> None:
        """Initialize the complete C.O.R.E. application."""

        self.logger.info("C.O.R.E. initialized.")

        self.events.emit(
            event_type=SYSTEM_STARTED,
            source="core",
            payload={"state": "running"},
        )

    def _register_health_checks(self) -> None:
        checks = {
            "runtime": self._check_runtime,
            "configuration": self._check_configuration,
            "logging": self._check_logging,
            "security": self._check_security,
            "resources": self._check_resources,
            "organization": self._check_organization,
            "events": self._check_events,
            "communication": self._check_communication,
            "routing": self._check_routing,
            "health": self._check_health,
            "services": self._check_services,
        }

        for component_id, check in checks.items():
            self.health.register(component_id, check)

    def _check_runtime(self) -> HealthResult:
        healthy = self.runtime.is_running

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

    def _check_configuration(self) -> HealthResult:
        healthy = self.configuration.is_running

        return HealthResult(
            component_id="configuration",
            status=(
                HealthStatus.HEALTHY
                if healthy
                else HealthStatus.UNHEALTHY
            ),
            message=(
                "Configuration manager is running."
                if healthy
                else "Configuration manager is not running."
            ),
        )

    def _check_logging(self) -> HealthResult:
        return HealthResult(
            component_id="logging",
            status=HealthStatus.HEALTHY,
            message="Logging is available.",
        )

    def _check_security(self) -> HealthResult:
        healthy = self.security.is_running

        return HealthResult(
            component_id="security",
            status=(
                HealthStatus.HEALTHY
                if healthy
                else HealthStatus.UNHEALTHY
            ),
            message=(
                "Security manager is running."
                if healthy
                else "Security manager is not running."
            ),
        )

    def _check_resources(self) -> HealthResult:
        return HealthResult(
            component_id="resources",
            status=HealthStatus.HEALTHY,
            message="Resource registry is available.",
        )

    def _check_organization(self) -> HealthResult:
        return HealthResult(
            component_id="organization",
            status=HealthStatus.HEALTHY,
            message="Organization engine is available.",
        )

    def _check_events(self) -> HealthResult:
        healthy = self.events.is_running

        return HealthResult(
            component_id="events",
            status=(
                HealthStatus.HEALTHY
                if healthy
                else HealthStatus.UNHEALTHY
            ),
            message=(
                "Event bus is running."
                if healthy
                else "Event bus is not running."
            ),
        )

    def _check_communication(self) -> HealthResult:
        healthy = self.communication.is_running

        return HealthResult(
            component_id="communication",
            status=(
                HealthStatus.HEALTHY
                if healthy
                else HealthStatus.UNHEALTHY
            ),
            message=(
                "Communication subsystem is running."
                if healthy
                else "Communication subsystem is not running."
            ),
        )

    def _check_routing(self) -> HealthResult:
        healthy = self.routing.is_running

        return HealthResult(
            component_id="routing",
            status=(
                HealthStatus.HEALTHY
                if healthy
                else HealthStatus.UNHEALTHY
            ),
            message=(
                "Router is running."
                if healthy
                else "Router is not running."
            ),
        )

    def _check_health(self) -> HealthResult:
        return HealthResult(
            component_id="health",
            status=HealthStatus.HEALTHY,
            message="Health monitor is available.",
        )

    def _check_services(self) -> HealthResult:
        running = [
            service
            for service in self.services.list()
            if service.status.value == "running"
        ]

        healthy = len(running) == self.services.count()

        return HealthResult(
            component_id="services",
            status=(
                HealthStatus.HEALTHY
                if healthy
                else HealthStatus.DEGRADED
            ),
            message=(
                f"{len(running)}/{self.services.count()} "
                "services are running."
            ),
        )

    def _shutdown_configuration(self) -> None:
        """Shutdown configuration infrastructure."""

        self.configuration.stop()

    def _shutdown_logging(self) -> None:
        """Shutdown logging infrastructure."""

    def _shutdown_security(self) -> None:
        self.security.stop()
        self.security.clear()

    def _shutdown_resources(self) -> None:
        self.resources.clear()

    def _shutdown_organization(self) -> None:
        self.organization.clear()

    def _shutdown_events(self) -> None:
        self.events.stop()
        self.events.clear()

    def _shutdown_communication(self) -> None:
        self.communication.stop()
        self.communication.clear()

    def _shutdown_routing(self) -> None:
        self.routing.stop()
        self.routing.clear()

    def _shutdown_health(self) -> None:
        self.health.stop()
        self.health.clear()

    def _shutdown_dependencies(self) -> None:
        self.dependencies.clear()

    def _shutdown_services(self) -> None:
        self.services.clear()

    def _shutdown(self) -> None:
        """
        Perform final application shutdown.

        Component-specific cleanup is handled by the runtime in reverse
        dependency order. This method only performs final application-level
        logging and lifecycle notification.
        """

        try:
            self.events.emit(
                event_type=SYSTEM_STOPPED,
                source="core",
                payload={"state": "stopped"},
            )
        except Exception:
            pass

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
