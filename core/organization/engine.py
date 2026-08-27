from collections import defaultdict
from typing import Iterable

from core.resources import Resource


class OrganizationEngine:
    """Organizes resources into searchable categories."""

    def __init__(self) -> None:
        self._categories: dict[str, set[str]] = defaultdict(set)

    def categorize(self, resource: Resource) -> None:
        """Add a resource to its resource-type category."""

        self._categories[resource.resource_type].add(
            resource.resource_id
        )

    def uncategorize(self, resource: Resource) -> None:
        """Remove a resource from its category."""

        category = self._categories.get(resource.resource_type)

        if category is None:
            return

        category.discard(resource.resource_id)

        if not category:
            del self._categories[resource.resource_type]

    def move(
        self,
        resource: Resource,
        resource_type: str,
    ) -> None:
        """Move a resource into another category."""

        self.uncategorize(resource)

        resource.resource_type = resource_type

        self.categorize(resource)

    def get_category(self, resource_type: str) -> list[str]:
        """Return resource IDs in a category."""

        return sorted(
            self._categories.get(resource_type, set())
        )

    def categories(self) -> list[str]:
        """Return all known categories."""

        return sorted(self._categories.keys())

    def contains(
        self,
        resource_type: str,
        resource_id: str,
    ) -> bool:
        """Check whether a resource belongs to a category."""

        return resource_id in self._categories.get(
            resource_type,
            set(),
        )

    def count(self) -> int:
        """Return the number of categories."""

        return len(self._categories)

    def clear(self) -> None:
        """Clear all organization data."""

        self._categories.clear()

    def __iter__(self) -> Iterable[str]:
        return iter(self._categories)