"""
Safe mathematical expression parser.

Normalizes intuitive notation (``^``, ``π``, ``√()``, ``°``, ``3!``,
implicit ``2x``) then parses with SymPy under a strict allowlist. No
``eval``/``exec`` on user input: an AST pre-scan rejects attribute
access, dunders, imports, and any name outside the allowlist before
SymPy ever sees the code.
"""

from __future__ import annotations

import ast
import re

from asis.calculator import errors

_DEGREE = re.compile(r"(\d+(?:\.\d+)?)\s*°")
_FACTORIAL = re.compile(r"(\([^()]*\)|\d+(?:\.\d+)?|[a-zA-Z_]\w*)\s*!(?!=)")

_ALIASES = (
    ("π", "pi"),
    ("τ", "tau"),
    ("φ", "phi"),
    ("√(", "sqrt("),
    ("÷", "/"),
    ("×", "*"),
    ("−", "-"),
    ("²", "**2"),
    ("³", "**3"),
)


def normalize(text: str) -> str:
    """Rewrite intuitive notation into parseable form."""
    out = text.strip()
    for alias, replacement in _ALIASES:
        out = out.replace(alias, replacement)
    out = _DEGREE.sub(r"(\1*pi/180)", out)
    # Factorial first so parse_expr never sees a bare `!`.
    previous = None
    while previous != out:
        previous = out
        out = _FACTORIAL.sub(r"factorial(\1)", out)
    return out


def _sympy_globals() -> dict:
    """Import SymPy lazily and build the name allowlist."""
    try:
        import sympy
    except ImportError as exc:
        raise errors.unavailable("sympy") from exc

    def _log10(value):
        return sympy.log(value, 10)

    def _log2(value):
        return sympy.log(value, 2)

    names = {
        "pi": sympy.pi,
        "e": sympy.E,
        "E": sympy.E,
        "tau": 2 * sympy.pi,
        "phi": sympy.GoldenRatio,
        "i": sympy.I,
        "I": sympy.I,
        "oo": sympy.oo,
        "sqrt": sympy.sqrt,
        "cbrt": sympy.cbrt,
        "Abs": sympy.Abs,
        "abs": sympy.Abs,
        "exp": sympy.exp,
        "ln": sympy.ln,
        "log": sympy.log,
        "log10": _log10,
        "log2": _log2,
        "sin": sympy.sin,
        "cos": sympy.cos,
        "tan": sympy.tan,
        "cot": sympy.cot,
        "sec": sympy.sec,
        "csc": sympy.csc,
        "asin": sympy.asin,
        "acos": sympy.acos,
        "atan": sympy.atan,
        "atan2": sympy.atan2,
        "sinh": sympy.sinh,
        "cosh": sympy.cosh,
        "tanh": sympy.tanh,
        "asinh": sympy.asinh,
        "acosh": sympy.acosh,
        "atanh": sympy.atanh,
        "factorial": sympy.factorial,
        "floor": sympy.floor,
        "ceiling": sympy.ceiling,
        "ceil": sympy.ceiling,
        "gcd": sympy.gcd,
        "lcm": sympy.lcm,
        "Max": sympy.Max,
        "Min": sympy.Min,
        "re": sympy.re,
        "im": sympy.im,
        "conjugate": sympy.conjugate,
        "arg": sympy.arg,
        "sign": sympy.sign,
        "Rational": sympy.Rational,
        "Integer": sympy.Integer,
        "Float": sympy.Float,
        "Number": sympy.Number,
        "Symbol": sympy.Symbol,
        "Add": sympy.Add,
        "Mul": sympy.Mul,
        "Pow": sympy.Pow,
        "Matrix": sympy.Matrix,
        "binomial": sympy.binomial,
        "fibonacci": sympy.fibonacci,
        "root": sympy.root,
    }
    return names


def _transformations():
    from sympy.parsing.sympy_parser import (
        convert_xor,
        function_exponentiation,
        implicit_multiplication_application,
        standard_transformations,
    )

    return standard_transformations + (
        convert_xor,
        function_exponentiation,
        implicit_multiplication_application,
    )


def _scan(node: ast.AST, allowed: set[str]) -> None:
    """Reject anything outside pure mathematics."""
    if isinstance(node, ast.Expression):
        _scan(node.body, allowed)
        return
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool | str) or not isinstance(
            node.value, int | float | complex
        ):
            raise errors.invalid_expression("literals outside mathematics")
        return
    if isinstance(node, ast.Name):
        if node.id not in allowed and not (
            len(node.id) == 1 and node.id.isalpha() and node.id.islower()
        ):
            raise errors.invalid_expression(f"unknown name '{node.id}'")
        return
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in allowed:
            raise errors.invalid_expression("function calls outside mathematics")
        numeric_ctor = node.func.id in ("Integer", "Float", "Rational", "Symbol")
        for arg in node.args:
            if (
                numeric_ctor
                and isinstance(arg, ast.Constant)
                and isinstance(arg.value, (int, float, str))
            ):
                continue
            _scan(arg, allowed)
        for keyword in node.keywords:
            _scan(keyword.value, allowed)
        return
    if isinstance(node, ast.BinOp):
        _scan(node.left, allowed)
        _scan(node.right, allowed)
        return
    if isinstance(node, ast.BoolOp):
        for value in node.values:
            _scan(value, allowed)
        return
    if isinstance(node, ast.UnaryOp):
        _scan(node.operand, allowed)
        return
    if isinstance(node, (ast.List, ast.Tuple)):
        for child in node.elts:
            _scan(child, allowed)
        return
    if isinstance(node, ast.IfExp):
        _scan(node.test, allowed)
        _scan(node.body, allowed)
        _scan(node.orelse, allowed)
        return
    raise errors.invalid_expression(f"unsupported syntax '{type(node).__name__}'")


def parse(text: str, extra_functions: dict | None = None):
    """Parse a mathematical expression string into a SymPy object.

    ``extra_functions`` extends the name allowlist (e.g. Derivative/Eq
    for ODEs); the AST scan still applies to every name used.
    """
    from sympy.parsing.sympy_parser import parse_expr, stringify_expr

    cleaned = normalize(text)
    allowed = _sympy_globals()
    if extra_functions:
        allowed.update(extra_functions)
    transformations = _transformations()
    try:
        code = stringify_expr(cleaned, dict(allowed), {}, transformations)
    except Exception as exc:
        raise errors.invalid_expression(f"could not parse expression ({exc})") from exc
    try:
        tree = ast.parse(code, mode="eval")
    except SyntaxError as exc:
        raise errors.invalid_expression("malformed expression") from exc
    _scan(tree, set(allowed))
    try:
        return parse_expr(code, local_dict=dict(allowed), global_dict={})
    except errors.CalculatorError:
        raise
    except Exception as exc:
        raise errors.invalid_expression(
            f"could not evaluate expression ({exc})"
        ) from exc


def parse_number(text: str) -> float:
    """Parse a plain numeric literal (no symbols) into a float."""
    from sympy import N

    expr = parse(text)
    if expr.free_symbols:
        raise errors.invalid_expression("expected a plain number")
    try:
        return float(N(expr))
    except Exception as exc:
        raise errors.domain_error(f"not a finite number ({exc})") from exc
