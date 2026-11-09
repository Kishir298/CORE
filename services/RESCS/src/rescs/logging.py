"""Logging foundation for RESCS."""

from __future__ import annotations

import logging
import sys

_FORMAT = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"

_configured = False
_handler_owned = False


def configure_logging(level: str = "INFO") -> None:
    """Install the root logger handler once for the process.

    Idempotent: repeated calls (multiple app factory invocations in tests)
    only adjust the level.
    """
    global _configured, _handler_owned
    root = logging.getLogger()
    root.setLevel(level.upper())
    if not _handler_owned:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(handler)
        _handler_owned = True
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger for the given module path."""
    return logging.getLogger(name)
