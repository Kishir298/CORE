"""
Logging handlers for A.S.I.S.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .formatters import ASISFormatter


def create_console_handler(level: int) -> logging.Handler:
    """Create a console logging handler."""
    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(ASISFormatter())
    return handler


def create_file_handler(
    log_directory: Path,
    level: int,
    filename: str = "asis.log",
) -> logging.Handler:
    """Create a size-bounded rotating file handler."""
    log_directory.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        log_directory / filename,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )

    handler.setLevel(level)
    handler.setFormatter(ASISFormatter())
    return handler
