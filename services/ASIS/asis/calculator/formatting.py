"""
Result formatting: exact strings, numeric rounding, matrix shaping.

Keeps SymPy output readable without losing exactness: exact forms stay
symbolic (``1/2``, ``sqrt(2)``), numerics round to the configured
precision, matrices render as nested lists.
"""

from __future__ import annotations


def format_matrix(text: str) -> str:
    """Render ``Matrix([[...], ...])`` as ``[[...], ...]`` when possible."""
    stripped = (text or "").strip()
    if stripped.startswith("Matrix(") and stripped.endswith(")"):
        inner = stripped[len("Matrix(") : -1].strip()
        if inner.startswith("["):
            return inner
    return stripped


def format_number(value: float, *, precision: int = 10) -> float:
    """Round a float to ``precision`` significant handling (plain round)."""
    try:
        rounded = round(float(value), precision)
    except Exception:
        return value
    if rounded == int(rounded) and abs(rounded) < 1e15:
        return rounded
    return rounded


def format_exact(text: str | None) -> str | None:
    """Normalize an exact-result string (matrix shaping included)."""
    if text is None:
        return None
    return format_matrix(str(text))
