from .models import OrganizationEntry


class OrganizationError(Exception):
    """Base organization error."""


class OrganizationEntryAlreadyExists(OrganizationError):
    """Raised when an organization entry already exists."""


class OrganizationEntryNotFound(OrganizationError):
    """Raised when an organization entry cannot be found."""


class OrganizationEngine:
    """Manages organized C.O.R.E. information."""

    def __init__(self, registry=None) -> None:
        self._entries: dict[str, OrganizationEntry] = {}
        self._registry = registry

    def attach_registry(self, registry) -> None:
        """Attach a resource registry for resource discovery."""

        self._registry = registry

    def add(self, entry: OrganizationEntry) -> OrganizationEntry:
        if entry.entry_id in self._entries:
            raise OrganizationEntryAlreadyExists(
                f"Organization entry already exists: {entry.entry_id}"
            )

        self._entries[entry.entry_id] = entry
        return entry

    def get(self, entry_id: str) -> OrganizationEntry:
        try:
            return self._entries[entry_id]
        except KeyError as exc:
            raise OrganizationEntryNotFound(
                f"Organization entry not found: {entry_id}"
            ) from exc

    def remove(self, entry_id: str) -> OrganizationEntry:
        entry = self.get(entry_id)
        del self._entries[entry_id]
        return entry

    def list(self) -> list[OrganizationEntry]:
        return list(self._entries.values())

    def by_category(self, category: str) -> list[OrganizationEntry]:
        return [
            entry
            for entry in self._entries.values()
            if entry.category == category
        ]

    def by_resource(self, resource_id: str) -> list[OrganizationEntry]:
        return [
            entry
            for entry in self._entries.values()
            if entry.resource_id == resource_id
        ]

    def categorize_resource(self, resource) -> OrganizationEntry:
        """
        Create or update an organization entry that links a resource.

        The entry category is taken from the resource type so resources can
        be discovered by category through the organization layer.
        """

        entry_id = f"resource:{resource.resource_id}"

        entry = OrganizationEntry(
            entry_id=entry_id,
            category=resource.resource_type,
            name=resource.name,
            resource_id=resource.resource_id,
            metadata={
                "resource_type": resource.resource_type,
                "owner": resource.owner,
            },
        )

        if entry_id in self._entries:
            existing = self._entries[entry_id]
            existing.category = entry.category
            existing.name = entry.name
            existing.resource_id = entry.resource_id
            existing.metadata = entry.metadata
            return existing

        self._entries[entry_id] = entry
        return entry

    def remove_resource(self, resource_id: str) -> None:
        """Remove organization entries linked to a resource."""

        for entry_id in [
            entry_id
            for entry_id, entry in self._entries.items()
            if entry.resource_id == resource_id
        ]:
            del self._entries[entry_id]

    def resource(self, resource_id: str):
        """
        Return the resource for an id by querying the attached registry.

        Resource discovery requires an attached registry and raises via the
        registry when the resource is unknown.
        """

        if self._registry is None:
            raise OrganizationError(
                "No resource registry is attached for discovery."
            )

        return self._registry.get(resource_id)

    def update(
        self,
        entry_id: str,
        *,
        category: str | None = None,
        name: str | None = None,
        resource_id: str | None = None,
        metadata: dict | None = None,
    ) -> OrganizationEntry:
        entry = self.get(entry_id)

        if category is not None:
            entry.category = category

        if name is not None:
            entry.name = name

        if resource_id is not None:
            entry.resource_id = resource_id

        if metadata is not None:
            entry.metadata = metadata

        return entry

    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()

    def __iter__(self):
        return iter(self._entries.values())
