"""
Arithmetic, scientific, trigonometric, and complex evaluation.

Parses one expression with SymPy and returns exact + numeric forms.
Angle mode (radians/degrees/gradians) applies to trig input: in degree
mode ``sin(30)`` means sin of 30 degrees; explicit ``30°`` is always
degrees. Inverse functions return results in the active angle mode.
"""

from __future__ import annotations

import math

from asis.calculator import errors
from asis.calculator.parser import parse

ANGLE_MODES = ("radians", "degrees", "gradians")

_INVERSE_FUNCS = ("asin", "acos", "atan", "atan2")


def _require_sympy():
    try:
        import sympy
    except ImportError as exc:
        raise errors.unavailable("sympy") from exc
    return sympy


def _check_domain(sympy, expr, operation: str):
    """Reject undefined results (complex infinity, NaN) deterministically."""
    try:
        if expr is sympy.zoo or expr is sympy.nan:
            raise errors.undefined(f"{operation} is undefined for this input")
    except errors.CalculatorError:
        raise
    except Exception:
        pass
    if getattr(expr, "is_infinite", False):
        raise errors.undefined(f"{operation} diverges for this input")


def _to_float(sympy, expr) -> float | None:
    try:
        value = float(sympy.N(expr))
    except Exception:
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def evaluate(
    expression: str, *, angle_mode: str = "radians"
) -> tuple[str, float | None]:
    """Evaluate an arithmetic/scientific expression.

    Returns ``(exact_string, numeric_or_None)``. Raises CalculatorError.
    """
    sympy = _require_sympy()
    if angle_mode not in ANGLE_MODES:
        raise errors.invalid_expression(f"unknown angle mode '{angle_mode}'")
    expr = parse(expression)
    if expr.free_symbols:
        raise errors.invalid_expression("expression has unsolved variables")
    try:
        simplified = sympy.simplify(expr)
    except Exception as exc:
        raise errors.too_complex(f"could not simplify ({exc})") from exc
    _check_domain(sympy, simplified, "evaluation")
    exact = str(simplified)
    return exact, _to_float(sympy, simplified)


def _wrap_angle(sympy, name: str, args: tuple, angle_mode: str):
    """Apply a trig function honoring the active angle mode."""
    func = getattr(sympy, name)
    if angle_mode == "radians":
        return func(*args)
    factor = sympy.pi / 180 if angle_mode == "degrees" else sympy.pi / 200
    if name in _INVERSE_FUNCS:
        result = func(*args)
        return result / factor
    scaled = tuple(arg * factor if i == 0 else arg for i, arg in enumerate(args))
    return func(*scaled)


def trig(
    name: str, args: list[str], *, angle_mode: str = "radians"
) -> tuple[str, float | None]:
    """Evaluate a named trig/hyperbolic function on parsed arguments."""
    sympy = _require_sympy()
    allowed = {
        "sin",
        "cos",
        "tan",
        "cot",
        "sec",
        "csc",
        "asin",
        "acos",
        "atan",
        "atan2",
        "sinh",
        "cosh",
        "tanh",
        "asinh",
        "acosh",
        "atanh",
    }
    if name not in allowed:
        raise errors.invalid_expression(f"unknown function '{name}'")
    if angle_mode not in ANGLE_MODES:
        raise errors.invalid_expression(f"unknown angle mode '{angle_mode}'")
    try:
        parsed = [parse(arg) for arg in args]
    except errors.CalculatorError:
        raise
    for value in parsed:
        if value.free_symbols:
            raise errors.invalid_expression("trig arguments must be numeric")
    try:
        result = sympy.simplify(_wrap_angle(sympy, name, tuple(parsed), angle_mode))
    except Exception as exc:
        raise errors.domain_error(f"{name} failed ({exc})") from exc
    _check_domain(sympy, result, name)
    return str(result), _to_float(sympy, result)


def complex_op(name: str, args: list[str]) -> tuple[str, float | None]:
    """Complex operations: abs/arg/conjugate/re/im/polar/rect/pow."""
    sympy = _require_sympy()
    if name not in ("abs", "arg", "conjugate", "re", "im", "polar", "rect", "pow"):
        raise errors.invalid_expression(f"unknown complex operation '{name}'")
    try:
        parsed = [parse(arg) for arg in args]
    except errors.CalculatorError:
        raise
    try:
        if name == "polar":
            if len(parsed) != 1:
                raise errors.invalid_expression("polar takes one argument")
            z = sympy.sympify(parsed[0])
            magnitude, angle = sympy.Abs(z), sympy.arg(z)
            result = (sympy.simplify(magnitude), sympy.simplify(angle))
            return f"({result[0]}, {result[1]})", _to_float(sympy, magnitude)
        if name == "rect":
            if len(parsed) != 2:
                raise errors.invalid_expression("rect takes magnitude and angle")
            result = sympy.simplify(parsed[0] * sympy.exp(sympy.I * parsed[1]))
        elif name == "pow":
            if len(parsed) != 2:
                raise errors.invalid_expression("pow takes base and exponent")
            result = sympy.simplify(sympy.Pow(parsed[0], parsed[1]))
        else:
            if len(parsed) != 1:
                raise errors.invalid_expression(f"{name} takes one argument")
            func = sympy.Abs if name == "abs" else getattr(sympy, name)
            result = sympy.simplify(func(parsed[0]))
    except errors.CalculatorError:
        raise
    except Exception as exc:
        raise errors.domain_error(f"complex {name} failed ({exc})") from exc
    return str(result), _to_float(sympy, result)
