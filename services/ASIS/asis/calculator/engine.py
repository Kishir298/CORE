"""
Calculator engine: operation dispatch, verification, resource limits.

Single entry point owned by A.S.I.S. All computation is local
(SymPy + standard library); the engine never touches the network and
never downloads anything. Results are verified independently where a
cheap independent check exists, and the verification record says
exactly what was checked.
"""

from __future__ import annotations

from asis.calculator import errors
from asis.calculator.models import CalculatorResult
from asis.calculator.operations import (
    DEFAULT_PRECISION,
    OPERATION_HANDLERS,
    OPERATIONS,
    OpContext,
)


class CalculatorEngine:
    """Deterministic local mathematics entry point.

    Split contract: this class owns configuration (limits, precision,
    angle mode) and dispatch; per-operation implementations live in
    :mod:`asis.calculator.operations` as pure functions of an explicit
    :class:`OpContext`. Keep it that way — do not move logic back here.
    """

    def __init__(
        self,
        *,
        max_expression_chars: int = 2_000,
        max_matrix_size: int = 10,
        precision: int = DEFAULT_PRECISION,
        angle_mode: str = "radians",
    ) -> None:
        self._max_chars = max(1, int(max_expression_chars))
        self._max_matrix = max(1, int(max_matrix_size))
        self._precision = max(0, int(precision))
        if angle_mode not in ("radians", "degrees", "gradians"):
            raise errors.invalid_expression(f"unknown angle mode '{angle_mode}'")
        self._angle_mode = angle_mode

    @property
    def angle_mode(self) -> str:
        return self._angle_mode

    # -- dispatch ---------------------------------------------------------
    def calculate(self, operation: str, params: dict | None = None) -> CalculatorResult:
        """Run one calculator operation over validated string params."""
        name = (operation or "").strip().lower()
        if name not in OPERATIONS:
            raise errors.invalid_expression(f"unknown operation '{name}'")
        ctx = OpContext(
            max_chars=self._max_chars,
            max_matrix=self._max_matrix,
            precision=self._precision,
            angle_mode=self._angle_mode,
        )
        return OPERATION_HANDLERS[name](ctx, dict(params or {}))

def build_engine_from_settings(settings_obj=None) -> CalculatorEngine:
    """Build the configured engine (limits, precision, angle mode)."""
    if settings_obj is None:
        from asis.configuration.settings import settings as settings_obj
    calc = settings_obj.calculator
    return CalculatorEngine(
        max_expression_chars=calc.max_expression_chars,
        max_matrix_size=calc.max_matrix_size,
        precision=calc.precision,
        angle_mode=calc.angle_mode,
    )
