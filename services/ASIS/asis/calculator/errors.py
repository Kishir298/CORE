"""
Stable calculator errors.

Every error carries a ``CALCULATION_*`` code safe to surface to users
and the model; messages never include tracebacks, paths, or secrets.
"""

from __future__ import annotations


class CalculatorError(Exception):
    """Calculator failure with a stable code safe for user output."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def disabled() -> CalculatorError:
    return CalculatorError(
        "CALCULATION_DISABLED",
        "CALCULATION_DISABLED: the calculator is disabled by configuration.",
    )


def unavailable(detail: str = "") -> CalculatorError:
    suffix = f" ({detail})" if detail else ""
    return CalculatorError(
        "CALCULATION_UNAVAILABLE",
        "CALCULATION_UNAVAILABLE: the local mathematics backend is not "
        f"installed{suffix}. Install it (`pip install sympy`).",
    )


def too_complex(reason: str = "expression too complex") -> CalculatorError:
    return CalculatorError(
        "CALCULATION_TOO_COMPLEX",
        f"CALCULATION_TOO_COMPLEX: {reason}.",
    )


def too_large(limit: int) -> CalculatorError:
    return CalculatorError(
        "CALCULATION_INPUT_TOO_LARGE",
        "CALCULATION_INPUT_TOO_LARGE: input exceeds the maximum of "
        f"{limit} characters.",
    )


def invalid_expression(reason: str) -> CalculatorError:
    return CalculatorError(
        "CALCULATION_INVALID_EXPRESSION",
        f"CALCULATION_INVALID_EXPRESSION: {reason}.",
    )


def domain_error(reason: str) -> CalculatorError:
    return CalculatorError(
        "CALCULATION_DOMAIN_ERROR",
        f"CALCULATION_DOMAIN_ERROR: {reason}.",
    )


def dimension_error(reason: str) -> CalculatorError:
    return CalculatorError(
        "CALCULATION_DIMENSION_ERROR",
        f"CALCULATION_DIMENSION_ERROR: {reason}.",
    )


def no_solution(detail: str = "no solution") -> CalculatorError:
    return CalculatorError(
        "CALCULATION_NO_SOLUTION",
        f"CALCULATION_NO_SOLUTION: {detail}.",
    )


def undefined(reason: str = "undefined result") -> CalculatorError:
    return CalculatorError(
        "CALCULATION_UNDEFINED",
        f"CALCULATION_UNDEFINED: {reason}.",
    )


def timeout() -> CalculatorError:
    return CalculatorError(
        "CALCULATION_TIMEOUT",
        "CALCULATION_TIMEOUT: the calculation exceeded its time budget.",
    )
