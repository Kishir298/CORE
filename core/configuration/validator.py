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
            "network",
            "rescs",
        ):
            if not config.has(section):
                continue

            value: Any = config.get(section)

            if not isinstance(value, dict):
                errors.append(
                    f"{section} must be a dictionary."
                )

        # Validate network.enabled if present
        if config.has("network"):
            network = config.get("network")
            if isinstance(network, dict) and "enabled" in network:
                if not isinstance(network["enabled"], bool):
                    errors.append("network.enabled must be a boolean.")

        # Validate communication.transport/host/port if present
        if config.has("communication"):
            comm = config.get("communication")
            if isinstance(comm, dict):
                if "transport" in comm and not isinstance(
                    comm["transport"], str
                ):
                    errors.append("communication.transport must be a string.")
                if "host" in comm and not isinstance(comm["host"], str):
                    errors.append("communication.host must be a string.")
                if "port" in comm and not isinstance(
                    comm["port"], (int, str)
                ):
                    errors.append(
                        "communication.port must be an integer or numeric string."
                    )
                elif "port" in comm and isinstance(comm["port"], str):
                    try:
                        int(comm["port"])
                    except ValueError:
                        errors.append(
                            "communication.port string must be numeric."
                        )
                # Port range validation
                if "port" in comm:
                    try:
                        port_val = int(comm["port"])  # type: ignore
                        if port_val < 0 or port_val > 65535:
                            errors.append(
                                "communication.port must be in range 0-65535."
                            )
                    except Exception:
                        pass
                # External host requires network.enabled context (warning, not error)
                if "host" in comm and comm["host"] == "0.0.0.0":
                    # Valid, but note that network.enabled should be true (enforced at runtime)
                    pass
                # TLS section — plaintext legacy preserved, so only type checks
                if "tls" in comm:
                    tls = comm["tls"]
                    if not isinstance(tls, dict):
                        errors.append("communication.tls must be a dictionary.")
                    else:
                        if "enabled" in tls and not isinstance(tls["enabled"], bool):
                            errors.append("communication.tls.enabled must be a boolean.")
                        if "certfile" in tls and not isinstance(tls["certfile"], str):
                            errors.append("communication.tls.certfile must be a string.")
                        if "keyfile" in tls and not isinstance(tls["keyfile"], str):
                            errors.append("communication.tls.keyfile must be a string.")
                        if "cafile" in tls and not isinstance(tls["cafile"], str):
                            errors.append("communication.tls.cafile must be a string.")
                        if "require_client_cert" in tls and not isinstance(tls["require_client_cert"], bool):
                            errors.append("communication.tls.require_client_cert must be a boolean.")

        # Validate security section if present
        if config.has("security"):
            sec = config.get("security")
            if isinstance(sec, dict):
                if "enforce_authorization" in sec and not isinstance(
                    sec["enforce_authorization"], bool
                ):
                    errors.append(
                        "security.enforce_authorization must be a boolean."
                    )
                if "provider" in sec and not isinstance(
                    sec["provider"], str
                ):
                    errors.append("security.provider must be a string.")
                if "authentication" in sec:
                    auth = sec["authentication"]
                    if isinstance(auth, dict) and "provider" in auth:
                        if not isinstance(auth["provider"], str):
                            errors.append(
                                "security.authentication.provider must be a string."
                            )

        # Validate rescs section if present
        if config.has("rescs"):
            rescs = config.get("rescs")
            if isinstance(rescs, dict):
                if "enabled" in rescs and not isinstance(
                    rescs["enabled"], bool
                ):
                    errors.append("rescs.enabled must be a boolean.")
                if "adapter" in rescs and not isinstance(
                    rescs["adapter"], str
                ):
                    errors.append("rescs.adapter must be a string.")
                if "path" in rescs and not isinstance(rescs["path"], str):
                    errors.append("rescs.path must be a string.")
                if "endpoint" in rescs and not isinstance(
                    rescs["endpoint"], str
                ):
                    errors.append("rescs.endpoint must be a string.")
                if "timeout" in rescs and not isinstance(
                    rescs["timeout"], (int, float, str)
                ):
                    errors.append("rescs.timeout must be a number or numeric string.")
                if "fallback" in rescs and not isinstance(
                    rescs["fallback"], bool
                ):
                    errors.append("rescs.fallback must be a boolean.")

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