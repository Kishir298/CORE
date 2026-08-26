from typing import Any

from .models import Configuration


class ConfigurationValidator:
    """Validates C.O.R.E. configuration."""

    REQUIRED_PATHS = (
        "core.name",
        "core.version",
        "environment",
    )

    def validate(self, config: Configuration) -> None:
        """Validate a configuration object."""

        errors: list[str] = []

        if not isinstance(config.data, dict):
            errors.append("Configuration data must be a dictionary.")

        if not isinstance(config.environment, str) or not config.environment:
            errors.append("Environment must be a non-empty string.")

        for path in self.REQUIRED_PATHS:
            if path == "environment":
                if not config.environment:
                    errors.append("Missing required configuration: environment")
                continue

            if not config.has(path):
                errors.append(f"Missing required configuration: {path}")

        if config.has("core.version"):
            version: Any = config.get("core.version")

            if not isinstance(version, str) or not version.strip():
                errors.append("core.version must be a non-empty string.")

        if errors:
            raise ValueError(
                "Invalid configuration:\n- " + "\n- ".join(errors)
            )
