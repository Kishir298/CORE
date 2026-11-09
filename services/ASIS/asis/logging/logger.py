"""
Centralized logging configuration for A.S.I.S.
"""

from __future__ import annotations

import logging

from asis.configuration.settings import settings

from .handlers import create_console_handler, create_file_handler

_ROOT_LOGGER_NAME = "asis"


def _resolve_log_level(level_name: str) -> int:
    """Convert a textual log level into a logging constant."""
    level = getattr(logging, level_name.upper(), None)

    if isinstance(level, int):
        return level

    return logging.INFO


def configure_logging() -> logging.Logger:
    """
    Configure the global A.S.I.S. logger.

    Safe to call multiple times; handlers are not duplicated.
    """
    logger = logging.getLogger(_ROOT_LOGGER_NAME)

    level = _resolve_log_level(settings.runtime.log_level)

    logger.setLevel(level)
    logger.propagate = False

    if logger.handlers:
        return logger

    logger.addHandler(create_console_handler(level))
    logger.addHandler(create_file_handler(settings.paths.logs, level))

    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Return a logger inside the A.S.I.S. logging hierarchy.

    Examples:
        get_logger()
        get_logger("ai")
        get_logger("voice.stt")
    """
    root = configure_logging()

    if not name:
        return root

    return root.getChild(name)
