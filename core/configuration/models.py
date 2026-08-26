from dataclasses import dataclass, field
from typing import Any


@dataclass
class Configuration:
    """
    Represents the complete C.O.R.E. configuration.

    Configuration values are stored as nested dictionaries so that
    components can use paths such as:

        core.name
        communication.port
        services.example.enabled
    """

    data: dict[str, Any] = field(default_factory=dict)
    environment: str = "development"

    def get(self, path: str, default: Any = None) -> Any:
        """
        Retrieve a configuration value using a dot-separated path.

        Example:
            config.get("core.name")
        """
        current: Any = self.data

        for key in path.split("."):
            if not isinstance(current, dict) or key not in current:
                return default

            current = current[key]

        return current

    def set(self, path: str, value: Any) -> None:
        """
        Set a configuration value using a dot-separated path.

        Example:
            config.set("core.name", "C.O.R.E.")
        """
        keys = path.split(".")
        current = self.data

        for key in keys[:-1]:
            existing = current.get(key)

            if not isinstance(existing, dict):
                existing = {}
                current[key] = existing

            current = existing

        current[keys[-1]] = value

    def has(self, path: str) -> bool:
        """
        Check whether a configuration path exists.
        """
        sentinel = object()
        return self.get(path, sentinel) is not sentinel

    def as_dict(self) -> dict[str, Any]:
        """Return the configuration data as a dictionary."""
        return self.data.copy()
