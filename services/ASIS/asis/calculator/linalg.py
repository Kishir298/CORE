"""
Vectors and matrices over SymPy with dimension validation.

Inputs are parsed from strings (``[1, 2, 3]``, ``[[1, 2], [3, 4]]``)
through the safe parser; every shape is validated before computing.
"""

from __future__ import annotations

from asis.calculator import errors
from asis.calculator.parser import parse
from asis.calculator.validation import check_matrix_shape


def _require_sympy():
    try:
        import sympy
    except ImportError as exc:
        raise errors.unavailable("sympy") from exc
    return sympy


def parse_matrix(text: str, *, max_size: int = 10):
    """Parse ``[[..], [..]]`` into a validated SymPy Matrix."""
    sympy = _require_sympy()
    try:
        expr = parse(text)
    except errors.CalculatorError:
        raise
    try:
        matrix = sympy.Matrix(expr)
    except Exception as exc:
        raise errors.invalid_expression(f"not a matrix ({exc})") from exc
    check_matrix_shape(matrix.rows, matrix.cols, max_size=max_size)
    return matrix


def parse_vector(text: str, *, max_size: int = 10):
    """Parse ``[..]`` into a validated SymPy Matrix column."""
    matrix = parse_matrix(text, max_size=max_size)
    if matrix.rows != 1 and matrix.cols != 1:
        raise errors.dimension_error("expected a vector (single row/column)")
    return matrix


def _fmt(sympy, value) -> str:
    try:
        return str(sympy.simplify(value))
    except Exception:
        return str(value)


def _num(sympy, value) -> float | None:
    try:
        import math

        number = float(sympy.N(value))
    except Exception:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def matrix_op(name: str, args: list[str], *, max_size: int = 10) -> dict:
    """Matrix operations; dimension errors are explicit, never silent."""
    sympy = _require_sympy()
    binary = {
        "add",
        "subtract",
        "multiply",
        "solve_linear",
        "augment",
    }
    unary = {
        "transpose",
        "determinant",
        "inverse",
        "rank",
        "trace",
        "eigenvalues",
        "eigenvectors",
        "row_echelon",
    }
    if name in ("scalar_multiply",):
        if len(args) != 2:
            raise errors.invalid_expression("scalar_multiply takes scalar, matrix")
        try:
            matrix = parse_matrix(args[1], max_size=max_size)
            scalar = parse(args[0])
        except errors.CalculatorError:
            raise
        if scalar.free_symbols:
            raise errors.invalid_expression("scalar must be numeric")
        result = scalar * matrix
        return {"result": _fmt(sympy, result), "shape": [result.rows, result.cols]}
    if name in binary:
        if len(args) != 2:
            raise errors.invalid_expression(f"{name} takes two matrices")
        left = parse_matrix(args[0], max_size=max_size)
        right = parse_matrix(args[1], max_size=max_size)
        try:
            if name == "add":
                result = left + right
            elif name == "subtract":
                result = left - right
            elif name == "multiply":
                result = left * right
            elif name == "augment":
                result = left.row_join(right)
            else:  # solve_linear: A x = b
                if left.rows != left.cols:
                    raise errors.dimension_error("coefficient matrix must be square")
                if right.cols != 1 or right.rows != left.rows:
                    raise errors.dimension_error(
                        "right-hand side must be a column of matching height"
                    )
                if left.det() == 0:
                    raise errors.no_solution("singular system (determinant is zero)")
                result = left.LUsolve(right)
        except errors.CalculatorError:
            raise
        except Exception as exc:
            raise errors.dimension_error(f"matrix {name} failed ({exc})") from exc
        return {"result": _fmt(sympy, result), "shape": [result.rows, result.cols]}
    if name in unary:
        if len(args) != 1:
            raise errors.invalid_expression(f"{name} takes one matrix")
        matrix = parse_matrix(args[0], max_size=max_size)
        try:
            if name == "transpose":
                result = matrix.T
                return {
                    "result": _fmt(sympy, result),
                    "shape": [result.rows, result.cols],
                }
            if name == "determinant":
                value = matrix.det()
                return {"result": _fmt(sympy, value), "numeric": _num(sympy, value)}
            if name == "trace":
                value = matrix.trace()
                return {"result": _fmt(sympy, value), "numeric": _num(sympy, value)}
            if name == "rank":
                return {"result": str(matrix.rank())}
            if name == "inverse":
                if matrix.rows != matrix.cols:
                    raise errors.dimension_error("inverse needs a square matrix")
                if matrix.det() == 0:
                    raise errors.no_solution("singular matrix has no inverse")
                result = matrix.inv()
                return {
                    "result": _fmt(sympy, result),
                    "shape": [result.rows, result.cols],
                }
            if name == "eigenvalues":
                values = matrix.eigenvals()
                return {
                    "result": str({str(k): v for k, v in values.items()}),
                }
            if name == "eigenvectors":
                vectors = matrix.eigenvects()
                out = []
                for value, multiplicity, basis in vectors:
                    out.append(
                        {
                            "value": str(value),
                            "multiplicity": int(multiplicity),
                            "vectors": [str(_fmt(sympy, b)) for b in basis],
                        }
                    )
                return {"result": str(out)}
            result = matrix.echelon_form()
            return {"result": _fmt(sympy, result), "shape": [result.rows, result.cols]}
        except errors.CalculatorError:
            raise
        except Exception as exc:
            raise errors.too_complex(f"matrix {name} failed ({exc})") from exc
    raise errors.invalid_expression(f"unknown matrix operation '{name}'")


def vector_op(name: str, args: list[str], *, max_size: int = 10) -> dict:
    """Vector operations with dimension checks."""
    sympy = _require_sympy()
    if name in ("add", "subtract", "dot", "cross"):
        if len(args) != 2:
            raise errors.invalid_expression(f"vector {name} takes two vectors")
        left = parse_vector(args[0], max_size=max_size)
        right = parse_vector(args[1], max_size=max_size)
        lflat = list(left)
        rflat = list(right)
        if len(lflat) != len(rflat):
            raise errors.dimension_error(
                f"vector lengths differ ({len(lflat)} vs {len(rflat)})"
            )
        try:
            if name == "add":
                result = sympy.Matrix(
                    [a + b for a, b in zip(lflat, rflat, strict=True)]
                )
                return {"result": _fmt(sympy, result)}
            if name == "subtract":
                result = sympy.Matrix(
                    [a - b for a, b in zip(lflat, rflat, strict=True)]
                )
                return {"result": _fmt(sympy, result)}
            if name == "dot":
                value = sum(a * b for a, b in zip(lflat, rflat, strict=True))
                value = sympy.simplify(value)
                return {"result": str(value), "numeric": _num(sympy, value)}
            if len(lflat) != 3:
                raise errors.dimension_error("cross product needs 3-D vectors")
            result = sympy.Matrix(lflat).cross(sympy.Matrix(rflat))
            return {"result": _fmt(sympy, result)}
        except errors.CalculatorError:
            raise
        except Exception as exc:
            raise errors.too_complex(f"vector {name} failed ({exc})") from exc
    if name in ("magnitude", "normalize"):
        if len(args) != 1:
            raise errors.invalid_expression(f"vector {name} takes one vector")
        vector = parse_vector(args[0], max_size=max_size)
        flat = list(vector)
        try:
            magnitude = sympy.simplify(sympy.sqrt(sum(a**2 for a in flat)))
            if name == "magnitude":
                return {"result": str(magnitude), "numeric": _num(sympy, magnitude)}
            if magnitude == 0:
                raise errors.domain_error("cannot normalize the zero vector")
            result = sympy.Matrix([sympy.simplify(a / magnitude) for a in flat])
            return {"result": _fmt(sympy, result)}
        except errors.CalculatorError:
            raise
        except Exception as exc:
            raise errors.too_complex(f"vector {name} failed ({exc})") from exc
    if name in ("scalar_multiply", "projection", "angle"):
        if len(args) != 2:
            raise errors.invalid_expression(f"vector {name} takes two arguments")
        try:
            if name == "scalar_multiply":
                scalar = parse(args[0])
                if scalar.free_symbols:
                    raise errors.invalid_expression("scalar must be numeric")
                vector = parse_vector(args[1], max_size=max_size)
                result = sympy.Matrix([sympy.simplify(scalar * a) for a in vector])
                return {"result": _fmt(sympy, result)}
            first = parse_vector(args[0], max_size=max_size)
            second = parse_vector(args[1], max_size=max_size)
            first_flat, second_flat = list(first), list(second)
            if len(first_flat) != len(second_flat):
                raise errors.dimension_error("vector lengths differ")
            dot = sympy.simplify(
                sum(a * b for a, b in zip(first_flat, second_flat, strict=True))
            )
            norm_sq = sympy.simplify(sum(b**2 for b in second_flat))
            if norm_sq == 0:
                raise errors.domain_error("projection onto the zero vector")
            if name == "projection":
                result = sympy.Matrix(
                    [sympy.simplify(dot * b / norm_sq) for b in second_flat]
                )
                return {"result": _fmt(sympy, result)}
            norm_a = sympy.sqrt(sum(a**2 for a in first_flat))
            norm_b = sympy.sqrt(norm_sq)
            if sympy.simplify(norm_a) == 0:
                raise errors.domain_error("angle with the zero vector")
            angle = sympy.simplify(sympy.acos(dot / (norm_a * norm_b)))
            return {"result": str(angle), "numeric": _num(sympy, angle)}
        except errors.CalculatorError:
            raise
        except Exception as exc:
            raise errors.too_complex(f"vector {name} failed ({exc})") from exc
    raise errors.invalid_expression(f"unknown vector operation '{name}'")
