from __future__ import annotations

from typing import Any

from .models import Configuration


class ConfigurationValidator:
    """
    Validates C.O.R.E. configuration.

    Validation is intentionally deterministic and side-effect free.
    Successful validation returns True; invalid configuration raises
    ValueError with all discovered problems.
    """

    REQUIRED_PATHS = (
        "core.name",
        "core.version",
        "environment",
    )

    def validate(self, config: Configuration) -> bool:
        """Validate a configuration object."""

        if not isinstance(config, Configuration):
            raise TypeError(
                "Configuration validator requires a Configuration object."
            )

        errors: list[str] = []

        if not isinstance(config.data, dict):
            errors.append(
                "Configuration data must be a dictionary."
            )

        if (
            not isinstance(config.environment, str)
            or not config.environment.strip()
        ):
            errors.append(
                "Environment must be a non-empty string."
            )

        for path in self.REQUIRED_PATHS:
            if path == "environment":
                continue

            if not config.has(path):
                errors.append(
                    f"Missing required configuration: {path}"
                )

        self._validate_core(config, errors)
        self._validate_environment(config, errors)
        self._validate_optional_sections(config, errors)
        self._validate_components(config, errors)

        if errors:
            raise ValueError(
                "Invalid configuration:\n- "
                + "\n- ".join(errors)
            )

        return True

    def is_valid(self, config: Configuration) -> bool:
        """Return whether a configuration is valid without raising."""

        try:
            self.validate(config)
        except (TypeError, ValueError):
            return False

        return True

    def validate_path(
        self,
        config: Configuration,
        path: str,
    ) -> bool:
        """Validate that a configuration path exists."""

        if not isinstance(config, Configuration):
            raise TypeError(
                "Configuration validator requires a Configuration object."
            )

        if not config.has(path):
            raise ValueError(
                f"Missing required configuration: {path}"
            )

        return True

    @staticmethod
    def _validate_core(
        config: Configuration,
        errors: list[str],
    ) -> None:
        """Validate the core configuration section."""

        if not config.has("core"):
            return

        core = config.get("core")

        if not isinstance(core, dict):
            errors.append(
                "core must be a dictionary."
            )
            return

        name = core.get("name")

        if not isinstance(name, str) or not name.strip():
            errors.append(
                "core.name must be a non-empty string."
            )

        version = core.get("version")

        if not isinstance(version, str) or not version.strip():
            errors.append(
                "core.version must be a non-empty string."
            )

    @staticmethod
    def _validate_environment(
        config: Configuration,
        errors: list[str],
    ) -> None:
        """Validate the environment configuration."""

        environment = config.environment

        if not isinstance(environment, str):
            return

        if environment.strip() != environment:
            errors.append(
                "Environment cannot contain leading or trailing whitespace."
            )

    @staticmethod
    def _validate_optional_sections(
        config: Configuration,
        errors: list[str],
    ) -> None:
        """Validate known optional configuration sections."""

        for section in (
            "communication",
            "services",
            "logging",
            "security",
            "health",
            "resources",
            "runtime",
        ):
            if not config.has(section):
                continue

            value: Any = config.get(section)

            if not isinstance(value, dict):
                errors.append(
                    f"{section} must be a dictionary."
                )

    @staticmethod
    def _validate_components(
        config: Configuration,
        errors: list[str],
    ) -> None:
        """Validate the component enable/disable configuration section."""

        if not config.has("components"):
            return

        components: Any = config.get("components")

        if not isinstance(components, dict):
            errors.append("components must be a dictionary.")
            return

        for name, settings in components.items():
            if not isinstance(name, str) or not name.strip():
                errors.append(
                    "Component names in 'components' must be "
                    "non-empty strings."
                )
                continue

            if not isinstance(settings, dict):
                errors.append(
                    f"components.{name} must be a dictionary."
                )
                continue

            if "enabled" not in settings:
                continue

            if not isinstance(settings["enabled"], bool):
                errors.append(
                    f"components.{name}.enabled must be a boolean."
                )