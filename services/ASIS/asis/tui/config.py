"""
TUI Configuration Persistence.

Handles loading and saving TUI-specific user preferences to tui.toml
in the user's config directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomli
import tomli_w

from asis.configuration import settings
from asis.configuration.paths import get_config_directory

# TUI config file name
TUI_CONFIG_FILENAME = "tui.toml"


def get_tui_config_path() -> Path:
    """Return the path to the TUI config file."""
    return get_config_directory() / "tui.toml"


def load_tui_config() -> dict[str, Any]:
    """Load TUI configuration from tui.toml.

    Returns an empty dict if the file doesn't exist or is invalid.
    """
    config_path = get_tui_config_path()
    if not config_path.exists():
        return {}

    try:
        with open(config_path, "rb") as f:
            return tomli.load(f)
    except (tomli.TOMLDecodeError, OSError):
        # If the file is corrupted or unreadable, return empty config
        return {}


def save_tui_config(config: dict[str, Any]) -> None:
    """Save TUI configuration to tui.toml."""
    config_path = get_tui_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(config_path, "wb") as f:
            tomli_w.dump(config, f)
    except OSError:
        # Best effort - don't crash if we can't write config
        pass


def load_tui_settings() -> dict[str, Any]:
    """Load TUI settings from the global settings and tui.toml.

    The priority is:
    1. Environment variables (highest)
    2. tui.toml file
    3. Built-in defaults (lowest)
    """
    # Start with defaults from global settings
    defaults = {
        "sidebar_collapsed": settings.tui.sidebar_collapsed,
        "theme": settings.tui.theme,
        "left_column_width": settings.tui.left_column_width,
    }

    # Override with tui.toml if it exists
    file_config = load_tui_config()
    for key in defaults:
        if key in file_config:
            defaults[key] = file_config[key]

    return defaults


def save_tui_setting(key: str, value: Any) -> None:
    """Save a single TUI setting to tui.toml."""
    config = load_tui_config()
    config[key] = value
    save_tui_config(config)


def save_all_tui_settings(
    sidebar_collapsed: bool | None = None,
    theme: str | None = None,
    left_column_width: int | None = None,
) -> None:
    """Save multiple TUI settings at once."""
    config = load_tui_config()

    if sidebar_collapsed is not None:
        config["sidebar_collapsed"] = sidebar_collapsed
    if theme is not None:
        config["theme"] = theme
    if left_column_width is not None:
        config["left_column_width"] = left_column_width

    save_tui_config(config)
