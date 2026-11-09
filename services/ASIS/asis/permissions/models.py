"""
Permission levels for A.S.I.S. tools and operations.
"""

from __future__ import annotations

from enum import IntEnum


class PermissionLevel(IntEnum):
    """
    Risk level required to perform an operation.

    Higher values represent greater potential impact.
    """

    SAFE = 0
    LOW = 1
    MODERATE = 2
    HIGH = 3
    CRITICAL = 4


def requires_confirmation(level: PermissionLevel) -> bool:
    """Return whether a permission level requires confirmation."""
    return level >= PermissionLevel.HIGH
