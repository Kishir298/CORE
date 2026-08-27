from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ServiceStatus(str, Enum):
    REGISTERED = "registered"
    INITIALIZING = "initializing"
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"


@dataclass
class Service:
    service_id: str
    name: str
    version: str
    dependencies: list[str] = field(default_factory=list)
    startup_priority: int = 100
    configuration: dict[str, Any] = field(default_factory=dict)
    status: ServiceStatus = ServiceStatus.REGISTERED
    health: str = "unknown"

    def mark_healthy(self) -> None:
        self.health = "healthy"

    def mark_unhealthy(self) -> None:
        self.health = "unhealthy"
