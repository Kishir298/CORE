"""
Environment configuration for A.S.I.S.

Environment variables override built-in defaults. A ``.env`` file in the
project root or user configuration directory is loaded when present.
Secrets must never be hardcoded here.

Reads are lazy: every ``get_*`` call consults the current process
environment (plus explicit programmatic overrides), so
``load_settings()`` always reflects the environment at call time.
A present-but-invalid value raises ``ConfigurationError``; it is never
silently replaced by the default. Empty values count as unset.

Precedence (highest wins): explicit overrides > process environment >
``.env`` files > built-in defaults.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv

from asis.errors import ConfigurationError

_PROJECT_ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"

# Explicit programmatic overrides (highest precedence). Used by
# ``load_settings(env=...)`` and tests; never mutated by app code.
_EXPLICIT: dict[str, str] = {}


def _load_env_files() -> None:
    """Load .env files (project root and user config directory)."""
    candidates: list[Path] = [_PROJECT_ROOT_ENV_FILE]

    try:
        from .paths import get_config_directory

        candidates.append(get_config_directory() / ".env")
    except Exception:  # pragma: no cover - defensive during bootstrap
        pass

    for candidate in candidates:
        if candidate.exists():
            # Existing process variables always win over .env content.
            load_dotenv(candidate, override=False)


def load_env_file(path: str | Path, override: bool = False) -> bool:
    """Load one extra ``.env`` file (tests/development). Returns True if read."""
    candidate = Path(path).expanduser()
    if not candidate.exists():
        return False
    load_dotenv(candidate, override=override)
    return True


def set_explicit(mapping: Mapping[str, str] | None) -> None:
    """Replace the explicit override mapping (use ``override_env`` instead)."""
    _EXPLICIT.clear()
    if mapping:
        _EXPLICIT.update({str(k): str(v) for k, v in mapping.items()})


@contextmanager
def override_env(mapping: Mapping[str, str]) -> Iterator[None]:
    """Temporarily layer explicit overrides (highest precedence)."""
    previous = dict(_EXPLICIT)
    _EXPLICIT.update({str(k): str(v) for k, v in mapping.items()})
    try:
        yield
    finally:
        _EXPLICIT.clear()
        _EXPLICIT.update(previous)


def _raw(name: str) -> str | None:
    """Return the raw value for a variable, or None when unset/empty."""
    if name in _EXPLICIT:
        value: str | None = _EXPLICIT[name]
    else:
        value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def get_string(name: str, default: str) -> str:
    """Return a string variable, or the default when unset/empty."""
    value = _raw(name)
    return value if value is not None else default


_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "enabled"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", "disabled"})


def get_bool(name: str, default: bool) -> bool:
    """Return a boolean variable; raise on present-but-unrecognized values."""
    value = _raw(name)
    if value is None:
        return default
    lowered = value.lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    raise ConfigurationError(
        f"Invalid configuration value for {name}: expected a boolean "
        f"({'/'.join(sorted(_TRUE_VALUES | _FALSE_VALUES))}), "
        f"received {value!r}."
    )


def get_int(name: str, default: int) -> int:
    """Return an integer variable; raise on present-but-invalid values."""
    value = _raw(name)
    if value is None:
        return default
    try:
        return int(value, 10)
    except ValueError:
        raise ConfigurationError(
            f"Invalid configuration value for {name}: expected an integer, "
            f"received {value!r}."
        ) from None


def get_bounded_int(name: str, default: int, low: int, high: int) -> int:
    """Return an int variable within [low, high]; raise when present-but-invalid."""
    value = _raw(name)
    if value is None:
        return default
    try:
        number = int(value, 10)
    except ValueError:
        raise ConfigurationError(
            f"Invalid configuration value for {name}: expected an integer, "
            f"received {value!r}."
        ) from None
    if number < low or number > high:
        raise ConfigurationError(
            f"Invalid configuration value for {name}: expected an integer "
            f"between {low} and {high}, received {value!r}."
        )
    return number


def get_port(name: str, default: int) -> int:
    """Return a validated TCP port (1-65535); raise when present-but-invalid."""
    return get_bounded_int(name, default, 1, 65535)


def get_float(name: str, default: float) -> float:
    """Return a float variable; raise on present-but-invalid values."""
    value = _raw(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        raise ConfigurationError(
            f"Invalid configuration value for {name}: expected a number, "
            f"received {value!r}."
        ) from None


def get_path(name: str) -> Path | None:
    """Return an optional directory override as an absolute expanded path."""
    value = _raw(name)
    if value is None:
        return None
    return Path(value).expanduser().absolute()


def get_list(name: str, default: str) -> list[str]:
    """Return a comma-separated list variable, or default split when unset/empty."""
    value = _raw(name)
    if value is None:
        return [item.strip() for item in default.split(",") if item.strip()]
    return [item.strip() for item in value.split(",") if item.strip()]


_load_env_files()
