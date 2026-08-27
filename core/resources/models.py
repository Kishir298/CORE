from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Resource:
    """Represents a resource registered with C.O.R.E."""

    resource_id: str
    name: str
    resource_type: str
    status: str = "offline"
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