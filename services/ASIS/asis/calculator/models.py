"""
Calculator result models.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CalculatorResult:
    """Structured outcome of a calculation (data, never action)."""

    operation: str
    expression: str
    exact_result: str | None = None
    numeric_result: float | None = None
    units: str | None = None
    variables: tuple[str, ...] = ()
    steps: tuple[str, ...] = ()
    verification: dict | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
