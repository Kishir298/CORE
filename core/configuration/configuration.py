from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from threading import RLock
from typing import Any


class ConfigurationError(Exception):
    """Base exception for C.O.R.E. configuration errors."""


class ConfigurationKeyError(ConfigurationError):
    """Raised when a requested configuration key does not exist."""


@dataclass
class Configuration:
    """
    Central runtime configuration store for C.O.R.E.

    Configuration supports:
    - Explicit values
    - Default values
    - Environment-variable overrides
    - Runtime updates
    - Nested configuration access
    - Snapshot/export operations
    """

    values: dict[str, Any] = field(default_factory=dict)
    defaults: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._lock = RLock()

        self.values = dict(self.values)
        self.defaults = dict(self.defaults)

    def get(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        """Return a configuration value."""

        if not key:
            raise ValueError("Configuration key cannot be empty.")

        with self._lock:
            if key in self.values:
                return self.values[key]

            if key in self.defaults:
                return self.defaults[key]

            return default

    def require(self, key: str) -> Any:
        """Return a configuration value or raise if it does not exist."""

        if not self.contains(key):
            raise ConfigurationKeyError(
                f"Configuration key not found: {key}"
            )

        return self.get(key)

    def set(self, key: str, value: Any) -> None:
        """Set or replace a configuration value."""

        if not key:
            raise ValueError("Configuration key cannot be empty.")

        with self._lock:
            self.values[key] = value

    def set_default(self, key: str, value: Any) -> None:
        """Set or replace a default configuration value."""

        if not key:
            raise ValueError("Configuration key cannot be empty.")

        with self._lock:
            self.defaults[key] = value

    def remove(self, key: str) -> Any:
        """Remove an explicit configuration value."""

        with self._lock:
            if key not in self.values:
                raise ConfigurationKeyError(
                    f"Configuration key not found: {key}"
                )

            return self.values.pop(key)

    def remove_default(self, key: str) -> Any:
        """Remove a default configuration value."""

        with self._lock:
            if key not in self.defaults:
                raise ConfigurationKeyError(
                    f"Default configuration key not found: {key}"
                )

            return self.defaults.pop(key)

    def contains(self, key: str) -> bool:
        """Return whether a configuration key exists."""

        with self._lock:
            return key in self.values or key in self.defaults

    def keys(self) -> list[str]:
        """Return all known configuration keys."""

        with self._lock:
            return list(dict.fromkeys(
                [*self.defaults.keys(), *self.values.keys()]
            ))

    def items(self) -> list[tuple[str, Any]]:
        """Return effective configuration values."""

        with self._lock:
            keys = list(dict.fromkeys(
                [*self.defaults.keys(), *self.values.keys()]
            ))

            return [
                (key, self.values[key] if key in self.values else self.defaults[key])
                for key in keys
            ]

    def update(
        self,
        values: Mapping[str, Any],
    ) -> None:
        """Update multiple configuration values."""

        if not isinstance(values, Mapping):
            raise TypeError("Configuration update must be a mapping.")

        with self._lock:
            for key, value in values.items():
                if not key:
                    raise ValueError("Configuration key cannot be empty.")

                self.values[key] = value

    def update_defaults(
        self,
        values: Mapping[str, Any],
    ) -> None:
        """Update multiple default values."""

        if not isinstance(values, Mapping):
            raise TypeError(
                "Configuration defaults update must be a mapping."
            )

        with self._lock:
            for key, value in values.items():
                if not key:
                    raise ValueError("Configuration key cannot be empty.")

                self.defaults[key] = value

    def get_nested(
        self,
        key: str,
        default: Any = None,
        separator: str = ".",
    ) -> Any:
        """
        Retrieve a nested value.

        Example:
            database.host
        """

        if not key:
            raise ValueError("Configuration key cannot be empty.")

        if not separator:
            raise ValueError("Separator cannot be empty.")

        parts = key.split(separator)

        current: Any = self.get(parts[0], default)

        if current is default:
            return default

        for part in parts[1:]:
            if not isinstance(current, Mapping):
                return default

            if part not in current:
                return default

            current = current[part]

        return current

    def load_environment(
        self,
        prefix: str = "CORE_",
    ) -> dict[str, str]:
        """
        Load matching environment variables.

        Environment names are converted to lowercase dotted keys.

        Example:
            CORE_DATABASE_HOST -> database.host
        """

        if not prefix:
            raise ValueError("Environment prefix cannot be empty.")

        loaded: dict[str, str] = {}

        with self._lock:
            for environment_key, value in os.environ.items():
                if not environment_key.startswith(prefix):
                    continue

                config_key = environment_key[len(prefix):].lower()

                if not config_key:
                    continue

                config_key = config_key.replace("__", ".")
                loaded[config_key] = value
                self.values[config_key] = value

        return loaded

    def snapshot(self) -> dict[str, Any]:
        """Return a copy of the effective configuration."""

        return dict(self.items())

    def clear(self) -> None:
        """Clear explicit configuration values."""

        with self._lock:
            self.values.clear()

    def clear_all(self) -> None:
        """Clear explicit and default configuration values."""

        with self._lock:
            self.values.clear()
            self.defaults.clear()

    def validate(self) -> bool:
        """
        Validate the configuration.

        The base configuration layer accepts any non-empty key. More
        specialized validation can be added by higher-level components.
        """

        with self._lock:
            keys = [
                *self.values.keys(),
                *self.defaults.keys(),
            ]

            return all(bool(key) for key in keys)
