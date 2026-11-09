"""
Logging formatters for A.S.I.S.
"""

from __future__ import annotations

import logging


class ASISFormatter(logging.Formatter):
    """Consistent human-readable formatter for A.S.I.S. logs."""

    def __init__(self) -> None:
        super().__init__(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
