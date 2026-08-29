from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Resource:
    """Represents a resource registered with C.O.R.E."""

    resource_id: str
    name: str
    resource_type: str
    status: str = "offline"
    owner: str | None = None
    source: str | None = None
    capabilities: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    connection_info: dict = field(default_factory=dict)
    last_seen: datetime | None = None
    registered_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def mark_seen(self) -> None:
        self.last_seen = datetime.now(timezone.utc)
        self.status = "online"

    def is_online(self) -> bool:
        return self.status == "online"

    def update_status(self, status: str) -> None:
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable representation for cross-system use."""

        return {
            "resource_id": self.resource_id,
            "name": self.name,
            "resource_type": self.resource_type,
            "status": self.status,
            "owner": self.owner,
            "source": self.source,
            "capabilities": list(self.capabilities),
            "metadata": dict(self.metadata),
            "connection_info": dict(self.connection_info),
            "last_seen": (
                self.last_seen.isoformat()
                if self.last_seen is not None
                else None
            ),
            "registered_at": self.registered_at.isoformat(),
        }
