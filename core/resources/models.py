from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Resource:
    """Represents a resource known to C.O.R.E."""

    resource_id: str
    name: str
    resource_type: str
    status: str = "offline"
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    connection_info: dict[str, Any] = field(default_factory=dict)
    registered_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    last_seen: datetime | None = None

    def mark_seen(self) -> None:
        """Update the resource's last-seen timestamp."""
        self.last_seen = datetime.now(timezone.utc)
        self.status = "online"
