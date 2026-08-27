from typing import Iterable

from core.errors import (
    ResourceAlreadyRegistered,
    ResourceNotFound,
)

from .models import Resource


class ResourceRegistry:
    """Central registry of resources known to C.O.R.E."""

    def __init__(self) -> None:
        self._resources: dict[str, Resource] = {}

    def register(self, resource: Resource) -> Resource:
        if resource.resource_id in self._resources:
            raise ResourceAlreadyRegistered(
                f"Resource already registered: {resource.resource_id}"
            )

        self._resources[resource.resource_id] = resource
        return resource

    def unregister(self, resource_id: str) -> Resource:
        resource = self.get(resource_id)
        del self._resources[resource_id]
        return resource

    def get(self, resource_id: str) -> Resource:
        try:
            return self._resources[resource_id]
        except KeyError as exc:
            raise ResourceNotFound(
                f"Resource not found: {resource_id}"
            ) from exc

    def update(
        self,
        resource_id: str,
        *,
        name: str | None = None,
        status: str | None = None,
        capabilities: list[str] | None = None,
        metadata: dict | None = None,
        connection_info: dict | None = None,
    ) -> Resource:
        resource = self.get(resource_id)

        if name is not None:
            resource.name = name

        if status is not None:
            resource.status = status

        if capabilities is not None:
            resource.capabilities = capabilities

        if metadata is not None:
            resource.metadata = metadata

        if connection_info is not None:
            resource.connection_info = connection_info

        return resource

    def mark_seen(self, resource_id: str) -> Resource:
        resource = self.get(resource_id)
        resource.mark_seen()
        return resource

    def list(
        self,
        *,
        resource_type: str | None = None,
        status: str | None = None,
    ) -> list[Resource]:
        resources = list(self._resources.values())

        if resource_type is not None:
            resources = [
                resource
                for resource in resources
                if resource.resource_type == resource_type
            ]

        if status is not None:
            resources = [
                resource
                for resource in resources
                if resource.status == status
            ]

        return resources

    def count(self) -> int:
        return len(self._resources)

    def clear(self) -> None:
        self._resources.clear()

    def __iter__(self) -> Iterable[Resource]:
        return iter(self._resources.values())