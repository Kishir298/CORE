"""
Validation helpers for A.S.I.S.
"""

from __future__ import annotations

from collections.abc import Iterable


def require_non_empty_string(value: str, name: str = "value") -> str:
    """Validate and return a non-empty string."""
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string.")

    value = value.strip()

    if not value:
        raise ValueError(f"{name} cannot be empty.")

    return value


def require_positive_integer(value: int, name: str = "value") -> int:
    """Validate a positive integer."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer.")

    if value <= 0:
        raise ValueError(f"{name} must be greater than zero.")

    return value


def require_one_of(
    value: str,
    allowed: Iterable[str],
    name: str = "value",
) -> str:
    """Validate that a value belongs to an allowed collection."""
    allowed_values = set(allowed)

    if value not in allowed_values:
        raise ValueError(f"{name} must be one of: {', '.join(sorted(allowed_values))}")

    return value
