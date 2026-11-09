"""
Shared runtime context for A.S.I.S.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuntimeContext:
    """Shared environment provided to runtime components."""

    services: dict[str, Any] = field(default_factory=dict)

    def register(self, name: str, service: Any) -> None:
        """Register a shared service."""
        if not name.strip():
            raise ValueError("Service name cannot be empty.")

        self.services[name] = service

    def get(self, name: str) -> Any | None:
        """Retrieve a registered service."""
        return self.services.get(name)

    def require(self, name: str) -> Any:
        """Retrieve a service or raise an error."""
        service = self.get(name)

        if service is None:
            raise KeyError(f"Runtime service not registered: {name}")

        return service

    def remove(self, name: str) -> Any | None:
        """Remove and return a service."""
        return self.services.pop(name, None)

    def clear(self) -> None:
        """Remove all registered services."""
        self.services.clear()
