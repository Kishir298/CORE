from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone


class IdentityType(str, Enum):
    DEVICE = "device"
    SERVICE = "service"
    USER = "user"


class Permission(str, Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"


@dataclass(frozen=True)
class Identity:
    """Represents an authenticated C.O.R.E. identity."""

    identity_id: str
    name: str
    identity_type: IdentityType
    permissions: frozenset[Permission] = field(default_factory=frozenset)
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
