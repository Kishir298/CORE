"""
Cross-platform filesystem paths for A.S.I.S.

Paths are resolved with ``platformdirs`` so no user or machine location
is hardcoded. All persistent A.S.I.S. data lives outside the repository.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir, user_data_dir

from . import defaults

# Directory names used below the platform-specific base locations.
_DATA_SUBDIR = "data"
_CACHE_SUBDIR = "cache"
_CONFIG_SUBDIR = "config"
_LOGS_SUBDIR = "logs"
_MEMORY_SUBDIR = "memory"
_RUNTIME_SUBDIR = "runtime"


def _with_name(base: Path, name: str) -> Path:
    """Return a subpath unless the base already ends with that name."""
    if base.name == name:
        return base
    return base / name


def _apply_override(default: Path, override: Path | None) -> Path:
    """Return an explicit directory override, or the platform default."""
    if override is not None:
        return override
    from . import environment

    names = {"data": "DATA", "config": "CONFIG", "cache": "CACHE",
             "logs": "LOG", "memory": "MEMORY", "runtime": "RUNTIME"}
    part = names.get(default.name)
    # platformdirs cache/config paths may already end in the requested name.
    if part:
        selected = environment.get_path(f"ASIS_{part}_DIRECTORY")
        if selected is not None:
            return selected
        data = environment.get_path("ASIS_DATA_DIRECTORY")
        if data is not None and part != "DATA":
            return data / default.name
    return default


def get_data_directory(override: Path | None = None) -> Path:
    """Return A.S.I.S. persistent application-data directory."""
    return _apply_override(
        _with_name(Path(user_data_dir(defaults.APP_NAME)), _DATA_SUBDIR), override
    )


def get_config_directory(override: Path | None = None) -> Path:
    """Return A.S.I.S. user configuration directory."""
    return _apply_override(
        _with_name(Path(user_config_dir(defaults.APP_NAME)), _CONFIG_SUBDIR),
        override,
    )


def get_cache_directory(override: Path | None = None) -> Path:
    """Return A.S.I.S. cache directory."""
    return _apply_override(
        _with_name(Path(user_cache_dir(defaults.APP_NAME)), _CACHE_SUBDIR), override
    )


def get_log_directory(override: Path | None = None) -> Path:
    """Return A.S.I.S. log directory."""
    return _apply_override(
        _with_name(Path(user_data_dir(defaults.APP_NAME)), _LOGS_SUBDIR), override
    )


def get_memory_directory(override: Path | None = None) -> Path:
    """Return A.S.I.S. persistent local-memory directory."""
    return _apply_override(
        _with_name(Path(user_data_dir(defaults.APP_NAME)), _MEMORY_SUBDIR), override
    )


def get_runtime_directory(override: Path | None = None) -> Path:
    """Return a temporary runtime directory, not for permanent data."""
    return _apply_override(
        Path(tempfile.gettempdir()) / defaults.APP_NAME / _RUNTIME_SUBDIR, override
    )


def ensure_directories() -> dict[str, Path]:
    """Create required A.S.I.S. directories and return them."""
    directories = {
        "data": get_data_directory(),
        "config": get_config_directory(),
        "cache": get_cache_directory(),
        "logs": get_log_directory(),
        "memory": get_memory_directory(),
        "runtime": get_runtime_directory(),
    }

    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=True)

    return directories
