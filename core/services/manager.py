from collections.abc import Iterable

from core.errors import (
    ServiceAlreadyRegistered,
    ServiceDependencyError,
    ServiceNotFound,
)

from .models import Service, ServiceStatus


class ServiceManager:
    """Manages the lifecycle and dependencies of C.O.R.E. services."""

    def __init__(self) -> None:
        self._services: dict[str, Service] = {}

    def register(self, service: Service) -> Service:
        if service.service_id in self._services:
            raise ServiceAlreadyRegistered(
                f"Service already registered: {service.service_id}"
            )

        self._services[service.service_id] = service
        return service

    def unregister(self, service_id: str) -> Service:
        service = self.get(service_id)

        if service.status in {
            ServiceStatus.RUNNING,
            ServiceStatus.STARTING,
            ServiceStatus.INITIALIZING,
        }:
            self.stop(service_id)

        del self._services[service_id]
        return service

    def get(self, service_id: str) -> Service:
        try:
            return self._services[service_id]
        except KeyError as exc:
            raise ServiceNotFound(
                f"Service not found: {service_id}"
            ) from exc

    def initialize(self, service_id: str) -> Service:
        service = self.get(service_id)

        if service.status == ServiceStatus.RUNNING:
            return service

        service.status = ServiceStatus.INITIALIZING
        service.status = ServiceStatus.STOPPED

        return service

    def start(self, service_id: str) -> Service:
        service = self.get(service_id)

        if service.status == ServiceStatus.RUNNING:
            return service

        self._validate_dependencies(service)

        for dependency_id in self._dependency_order(service_id):
            dependency = self.get(dependency_id)

            if dependency.status != ServiceStatus.RUNNING:
                self.start(dependency_id)

        service.status = ServiceStatus.STARTING

        try:
            service.status = ServiceStatus.RUNNING
            service.mark_healthy()
        except Exception:
            service.status = ServiceStatus.FAILED
            service.mark_unhealthy()
            raise

        return service

    def stop(self, service_id: str) -> Service:
        service = self.get(service_id)

        dependents = [
            other
            for other in self._services.values()
            if service_id in other.dependencies
            and other.status == ServiceStatus.RUNNING
        ]

        for dependent in dependents:
            self.stop(dependent.service_id)

        if service.status != ServiceStatus.RUNNING:
            service.status = ServiceStatus.STOPPED
            return service

        service.status = ServiceStatus.STOPPING
        service.status = ServiceStatus.STOPPED
        service.health = "unknown"

        return service

    def restart(self, service_id: str) -> Service:
        self.stop(service_id)
        return self.start(service_id)

    def status(self, service_id: str) -> ServiceStatus:
        return self.get(service_id).status

    def health_check(self, service_id: str) -> str:
        service = self.get(service_id)

        if service.status == ServiceStatus.RUNNING:
            service.mark_healthy()
        else:
            service.mark_unhealthy()

        return service.health

    def list(self) -> list[Service]:
        return list(self._services.values())

    def count(self) -> int:
        return len(self._services)

    def clear(self) -> None:
        self._services.clear()

    def _validate_dependencies(self, service: Service) -> None:
        for dependency_id in service.dependencies:
            if dependency_id not in self._services:
                raise ServiceDependencyError(
                    f"Missing dependency '{dependency_id}' "
                    f"for service '{service.service_id}'"
                )

    def _dependency_order(self, service_id: str) -> list[str]:
        order: list[str] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(current_id: str) -> None:
            if current_id in visiting:
                raise ServiceDependencyError(
                    f"Circular dependency detected involving: {current_id}"
                )

            if current_id in visited:
                return

            visiting.add(current_id)

            service = self.get(current_id)

            for dependency_id in sorted(
                service.dependencies,
                key=lambda dependency: self.get(dependency).startup_priority,
            ):
                if dependency_id not in self._services:
                    raise ServiceDependencyError(
                        f"Missing dependency '{dependency_id}' "
                        f"for service '{current_id}'"
                    )

                visit(dependency_id)

            visiting.remove(current_id)
            visited.add(current_id)

            if current_id != service_id:
                order.append(current_id)

        visit(service_id)

        return order

    def __iter__(self) -> Iterable[Service]:
        return iter(self._services.values())
