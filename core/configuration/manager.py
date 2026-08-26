from pathlib import Path
from typing import Any

from .loader import ConfigurationLoader
from .models import Configuration
from .validator import ConfigurationValidator


class ConfigurationManager:
    """Public interface for C.O.R.E. configuration."""

    def __init__(
        self,
        loader: ConfigurationLoader | None = None,
        validator: ConfigurationValidator | None = None,
    ) -> None:
        self._loader = loader or ConfigurationLoader()
        self._validator = validator or ConfigurationValidator()
        self._configuration: Configuration | None = None

    def load(
        self,
        path: str | Path,
        environment: str = "development",
    ) -> Configuration:
        """Load and validate configuration from a YAML file."""

        configuration = self._loader.load(
            path,
            environment=environment,
        )

        self._validator.validate(configuration)
        self._configuration = configuration

        return configuration

    def set(self, path: str, value: Any) -> None:
        """Set a configuration value."""

        configuration = self._require_configuration()
        configuration.set(path, value)

    def get(self, path: str, default: Any = None) -> Any:
        """Get a configuration value."""

        configuration = self._require_configuration()
        return configuration.get(path, default)

    def has(self, path: str) -> bool:
        """Check whether a configuration value exists."""

        configuration = self._require_configuration()
        return configuration.has(path)

    def validate(self) -> None:
        """Validate the currently loaded configuration."""

        configuration = self._require_configuration()
        self._validator.validate(configuration)

    def current(self) -> Configuration:
        """Return the currently loaded configuration."""

        return self._require_configuration()

    def _require_configuration(self) -> Configuration:
        if self._configuration is None:
            raise RuntimeError("No configuration has been loaded.")

        return self._configuration
