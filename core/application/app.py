from pathlib import Path

from core.communication import LocalCommunication
from core.configuration import ConfigurationManager
from core.dependencies import DependencyManager
from core.events import (
    COMPONENT_STARTED,
    EventBus,
    HEALTH_CHANGED,
    MESSAGE_SENT,
    RESOURCE_REGISTERED,
    RESOURCE_REMOVED,
    SERVICE_EXECUTED,
    SERVICE_FAILED,
    SYSTEM_STARTED,
    SYSTEM_STOPPED,
)
from core.health import HealthMonitor, HealthResult, HealthStatus
from core.logging import CoreLogger
from core.organization import OrganizationEngine
from core.resources import Resource, ResourceRegistry
from core.routing import Router
from core.runtime import Runtime
from core.security import SecurityManager
from core.services import (
    Service,
    ServiceDispatcher,
    ServiceManager,
)

DEFAULT_CONFIG_PATH = Path("config/core.yaml")


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

        self.events = EventBus()
        self.communication = LocalCommunication(
            on_delivery=self._emit_message_sent
        )
        self.resources = ResourceRegistry()
        self.organization = OrganizationEngine(registry=self.resources)
        self.resources.attach_organization(self.organization)
        self.health = HealthMonitor(on_change=self._emit_health_changed)
        self.dependencies = DependencyManager()
        self.security = SecurityManager()
        self.services = ServiceManager()
        self.routing = Router(self.communication)
        self.dispatcher = ServiceDispatcher(
            self.services,
            emitter=self._emit_service_event,
        )

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
        """Activate the security infrastructure and bridge its events."""

        self.security.start()

        self.security.register_event_handler(
            self._bridge_security_event
        )

    def _initialize_resources(self) -> None:
        """Activate the resource infrastructure."""

    def _initialize_organization(self) -> None:
        """Activate the organization infrastructure."""

    def _initialize_events(self) -> None:
        """Activate the event subsystem and attach event consumers."""

        self.events.start()
        self._attach_event_consumers()

    def _initialize_communication(self) -> None:
        """Activate the communication subsystem."""

        self.communication.start()

    def _initialize_routing(self) -> None:
        """Activate the routing subsystem and register service routes."""

        self.routing.start()
        self._register_service_routes()

    def _initialize_health(self) -> None:
        """Activate health monitoring and register component checks."""

        self.health.start()
        self._register_health_checks()

    def _initialize_dependencies(self) -> None:
        """Mark the dependency registry as active."""

        self.dependencies.validate()

    def _initialize_services(self) -> None:
        """Start C.O.R.E. internal services and expose their operations."""

        self._register_service_capabilities()
        self._register_service_endpoints()

        for service in self.services.list():
            try:
                self.services.start(service.service_id)
            except Exception as exc:
                self.logger.error(
                    f"Failed to start internal service "
                    f"'{service.service_id}': {exc}"
                )
                raise

    def _register_service_capabilities(self) -> None:
        """Register real operation handlers for internal services."""

        self.services.register_handler(
            "resources",
            "list",
            lambda: {
                "resources": [
                    {
                        "id": resource.resource_id,
                        "name": resource.name,
                        "type": resource.resource_type,
                        "status": resource.status,
                    }
                    for resource in self.resources
                ]
            },
        )

        self.services.register_handler(
            "resources",
            "get",
            lambda resource_id: {
                "resource": self._resource_snapshot(
                    self.resources.get(resource_id)
                )
            },
        )

        self.services.register_handler(
            "resources",
            "register",
            lambda resource_id, name, resource_type, **kwargs: (
                self._register_resource(
                    resource_id=resource_id,
                    name=name,
                    resource_type=resource_type,
                    **kwargs,
                )
            ),
        )

        self.services.register_handler(
            "resources",
            "discover",
            lambda **kwargs: {
                "resources": [
                    self._resource_snapshot(resource)
                    for resource in self.resources.discover(**kwargs)
                ]
            },
        )

        self.services.register_handler(
            "resources",
            "update",
            lambda resource_id, **kwargs: {
                "resource": self._resource_snapshot(
                    self.resources.update(resource_id, **kwargs)
                )
            },
        )

        self.services.register_handler(
            "resources",
            "remove",
            lambda resource_id: self._remove_resource(resource_id),
        )

        self.services.register_handler(
            "resources",
            "category",
            lambda resource_id: {
                "organization_entries": [
                    {
                        "id": entry.entry_id,
                        "category": entry.category,
                        "name": entry.name,
                        "resource_id": entry.resource_id,
                    }
                    for entry in self.organization.by_resource(resource_id)
                ]
            },
        )

        self.services.register_handler(
            "organization",
            "list",
            lambda: {
                "entries": [
                    {
                        "id": entry.entry_id,
                        "category": entry.category,
                        "name": entry.name,
                        "resource_id": entry.resource_id,
                    }
                    for entry in self.organization
                ]
            },
        )

        self.services.register_handler(
            "organization",
            "by_category",
            lambda category: {
                "entries": [
                    {
                        "id": entry.entry_id,
                        "category": entry.category,
                        "name": entry.name,
                        "resource_id": entry.resource_id,
                    }
                    for entry in self.organization.by_category(category)
                ]
            },
        )

        self.services.register_handler(
            "routing",
            "routes",
            lambda: {"count": self.routing.count()},
        )

        self.services.register_handler(
            "health",
            "status",
            lambda: {
                "checks": [
                    {
                        "component_id": result.component_id,
                        "status": result.status.value,
                        "message": result.message,
                    }
                    for result in self.health.check_all()
                ],
                "overall": self.health.overall_status().value,
            },
        )

        self.services.register_handler(
            "health",
            "overall",
            lambda: {"overall": self.health.overall_status().value},
        )

        self.services.register_handler(
            "communication",
            "status",
            lambda: {
                "running": self.communication.is_running,
                "endpoints": self.communication.endpoint_count(),
                "messages": self.communication.message_count(),
            },
        )

        self.services.register_handler(
            "events",
            "status",
            lambda: {
                "running": self.events.is_running,
                "published": self.events.event_count(),
                "subscribers": self.events.subscriber_count(),
            },
        )

    def _register_service_endpoints(self) -> None:
        """Register transport endpoints that dispatch to services."""

        for service in self.services.list():
            endpoint = self.dispatcher.endpoint_for(service.service_id)

            if self.communication.has_endpoint(endpoint):
                continue

            self.communication.register(endpoint, self.dispatcher.handle)

    def _register_service_routes(self) -> None:
        """Register routes from application message types to services."""

        routes = {
            "RESOURCES.LIST": "service:resources",
            "HEALTH.STATUS": "service:health",
            "ORGANIZATION.LIST": "service:organization",
            "ROUTING.ROUTES": "service:routing",
            "COMMUNICATION.STATUS": "service:communication",
        }

        for message_type, destination in routes.items():
            if not self.routing.has_route(message_type):
                self.routing.add_route(message_type, destination)

    def _register_resource(
        self,
        resource_id: str,
        name: str,
        resource_type: str,
        **kwargs,
    ) -> dict:
        """Register a resource and return its snapshot."""

        resource = Resource(
            resource_id=resource_id,
            name=name,
            resource_type=resource_type,
            **kwargs,
        )

        self.resources.register(resource)

        self._emit_resource_event(RESOURCE_REGISTERED, resource)

        return {"resource": self._resource_snapshot(resource)}

    def _remove_resource(self, resource_id: str) -> dict:
        """Remove a resource and publish a removal event."""

        resource = self.resources.unregister(resource_id)

        self._emit_resource_event(RESOURCE_REMOVED, resource)

        return {"removed": resource.resource_id}

    @staticmethod
    def _resource_snapshot(resource: Resource) -> dict:
        """Return a serializable snapshot of a resource."""

        return {
            "id": resource.resource_id,
            "name": resource.name,
            "type": resource.resource_type,
            "status": resource.status,
            "owner": resource.owner,
            "source": resource.source,
            "capabilities": list(resource.capabilities),
            "metadata": dict(resource.metadata),
        }

    def _initialize(self) -> None:
        """Initialize the complete C.O.R.E. application."""

        self.logger.info("C.O.R.E. initialized.")

        for component in self.runtime.initialized_components():
            self.events.emit(
                event_type=COMPONENT_STARTED,
                source="core",
                payload={"component": component},
            )

    def _emit_message_sent(self, message) -> None:
        """Publish a communication event for a delivered message."""

        self.events.emit(
            event_type=MESSAGE_SENT,
            source=message.source,
            payload={
                "destination": message.destination,
                "message_type": message.message_type,
                "message_id": message.message_id,
            },
        )

    def _emit_service_event(self, event_type: str, source: str, payload: dict) -> None:
        """Publish a service lifecycle/execution event."""

        self.events.emit(
            event_type=event_type,
            source=source,
            payload=payload,
        )

    def _emit_resource_event(self, event_type: str, resource: Resource) -> None:
        """Publish a resource lifecycle event."""

        self.events.emit(
            event_type=event_type,
            source="resources",
            payload={"resource_id": resource.resource_id},
        )

    def _emit_health_changed(self, result) -> None:
        """Publish a health change event for a component status transition."""

        self.events.emit(
            event_type=HEALTH_CHANGED,
            source="health",
            payload={
                "component_id": result.component_id,
                "status": result.status.value,
            },
        )

    def _bridge_security_event(self, event: dict) -> None:
        """Bridge SecurityManager observer events onto the event bus."""

        self.events.emit(
            event_type=event["event_type"],
            source="security",
            payload={
                "identity_id": event["identity_id"],
                "success": event["success"],
            },
        )

    def _attach_event_consumers(self) -> None:
        """Subscribe C.O.R.E. consumers to event bus events."""

        self.events.subscribe(
            "SYSTEM_STARTED",
            self._consume_system_started,
        )

        self.events.subscribe(
            "SYSTEM_STOPPED",
            self._consume_system_stopped,
        )

        self.events.subscribe(
            "SERVICE_FAILED",
            self._consume_service_failed,
        )

    def _consume_system_started(self, event) -> None:
        """React to application startup by refreshing health."""

        self.health.check_all()

    def _consume_system_stopped(self, event) -> None:
        """React to application shutdown."""

        self.logger.info("System stopped event consumed.")

    def _consume_service_failed(self, event) -> None:
        """Log a service failure event."""

        self.logger.error(
            f"Service event failure: "
            f"{event.payload.get('service_id')}."
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
            message=f"{self.resources.count()} resources registered.",
        )

    def _check_organization(self) -> HealthResult:
        return HealthResult(
            component_id="organization",
            status=HealthStatus.HEALTHY,
            message=f"{self.organization.count()} organization entries.",
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
        if not self.communication.is_running:
            return HealthResult(
                component_id="communication",
                status=HealthStatus.UNHEALTHY,
                message="Communication subsystem is not running.",
            )

        return HealthResult(
            component_id="communication",
            status=HealthStatus.HEALTHY,
            message=(
                f"Communication online; "
                f"{self.communication.count()} channels."
            ),
        )

    def _check_routing(self) -> HealthResult:
        if not self.routing.is_running:
            return HealthResult(
                component_id="routing",
                status=HealthStatus.UNHEALTHY,
                message="Router is not running.",
            )

        return HealthResult(
            component_id="routing",
            status=HealthStatus.HEALTHY,
            message=f"Router online; {self.routing.count()} routes.",
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

        self.events.emit(
            event_type=SYSTEM_STARTED,
            source="core",
            payload={"state": "running"},
        )

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
