"""
Symbolic mathematics: algebra, equations, inequalities, calculus.

Thin, validated wrappers over SymPy with honest outcome reporting:
exact solutions, no-solution vs infinite-solution distinction, and
explicit failure instead of fabricated results.
"""

from __future__ import annotations

from asis.calculator import errors
from asis.calculator.parser import parse
from asis.calculator.validation import check_poly_degree


def _require_sympy():
    try:
        import sympy
    except ImportError as exc:
        raise errors.unavailable("sympy") from exc
    return sympy


def _symbols(sympy, names: list[str]):
    try:
        return [sympy.Symbol(name) for name in names]
    except Exception as exc:
        raise errors.invalid_expression(f"bad variable names ({exc})") from exc


def _split_equation(text: str) -> tuple[str, str]:
    if text.count("=") != 1:
        raise errors.invalid_expression("equation needs exactly one '='")
    left, right = text.split("=", 1)
    if not left.strip() or not right.strip():
        raise errors.invalid_expression("equation has an empty side")
    return left.strip(), right.strip()


def _degree_of(sympy, expr, var) -> int:
    try:
        poly = sympy.Poly(expr, var)
        return int(poly.degree())
    except Exception:
        return -1


def simplify_expr(text: str) -> str:
    sympy = _require_sympy()
    try:
        return str(sympy.simplify(parse(text)))
    except errors.CalculatorError:
        raise
    except Exception as exc:
        raise errors.too_complex(f"simplification failed ({exc})") from exc


def expand_expr(text: str) -> str:
    sympy = _require_sympy()
    try:
        return str(sympy.expand(parse(text)))
    except errors.CalculatorError:
        raise
    except Exception as exc:
        raise errors.too_complex(f"expansion failed ({exc})") from exc


def factor_expr(text: str) -> str:
    sympy = _require_sympy()
    try:
        return str(sympy.factor(parse(text)))
    except errors.CalculatorError:
        raise
    except Exception as exc:
        raise errors.too_complex(f"factorization failed ({exc})") from exc


def collect_expr(text: str, variable: str) -> str:
    sympy = _require_sympy()
    var = _symbols(sympy, [variable])[0]
    try:
        return str(sympy.collect(sympy.expand(parse(text)), var))
    except errors.CalculatorError:
        raise
    except Exception as exc:
        raise errors.too_complex(f"collection failed ({exc})") from exc


def substitute(text: str, variable: str, value: str) -> str:
    sympy = _require_sympy()
    var = _symbols(sympy, [variable])[0]
    try:
        result = sympy.simplify(parse(text).subs(var, parse(value)))
    except errors.CalculatorError:
        raise
    except Exception as exc:
        raise errors.too_complex(f"substitution failed ({exc})") from exc
    return str(result)


def solve_equation(text: str, variable: str) -> dict:
    """Solve one equation; classify exact / none / infinite honestly."""
    sympy = _require_sympy()
    var = _symbols(sympy, [variable])[0]
    left, right = _split_equation(text)
    try:
        difference = sympy.simplify(parse(left) - parse(right))
    except errors.CalculatorError:
        raise
    if difference == 0:
        return {"status": "infinite", "solutions": []}
    degree = _degree_of(sympy, difference, var)
    if degree >= 0:
        check_poly_degree(degree)
    try:
        solutions = sympy.solve(difference, var, dict=False)
    except Exception as exc:
        raise errors.too_complex(f"solver failed ({exc})") from exc
    if not solutions:
        raise errors.no_solution("equation has no solution")
    return {"status": "exact", "solutions": [str(s) for s in solutions]}


def solve_system(equations: list[str], variables: list[str]) -> dict:
    """Solve simultaneous equations over the given variables."""
    sympy = _require_sympy()
    if not equations or not variables:
        raise errors.invalid_expression("system needs equations and variables")
    if len(equations) > 6 or len(variables) > 6:
        raise errors.too_complex("system exceeds 6 equations/variables")
    syms = _symbols(sympy, variables)
    try:
        exprs = []
        for item in equations:
            left, right = _split_equation(item)
            exprs.append(parse(left) - parse(right))
    except errors.CalculatorError:
        raise
    try:
        solutions = sympy.solve(exprs, syms, dict=True)
    except Exception as exc:
        raise errors.too_complex(f"system solver failed ({exc})") from exc
    if not solutions:
        raise errors.no_solution("system has no solution")
    out = []
    for solution in solutions:
        out.append({str(var): str(solution[var]) for var in syms if var in solution})
    if not out or all(not entry for entry in out):
        return {"status": "infinite", "solutions": []}
    return {"status": "exact", "solutions": out}


def solve_inequality(text: str, variable: str) -> dict:
    """Solve an inequality; return interval/set notation."""
    sympy = _require_sympy()
    var = _symbols(sympy, [variable])[0]
    matched = None
    for token in ("<=", ">=", "<", ">"):
        if token in text:
            matched = token
            break
    if matched is None:
        raise errors.invalid_expression("inequality needs <, <=, > or >=")
    left, right = text.split(matched, 1)
    relators = {"<": sympy.Lt, "<=": sympy.Le, ">": sympy.Gt, ">=": sympy.Ge}
    try:
        relation = relators[matched](parse(left.strip()), parse(right.strip()))
        result = sympy.solveset(relation, var, sympy.S.Reals)
    except errors.CalculatorError:
        raise
    except Exception as exc:
        raise errors.too_complex(f"inequality solver failed ({exc})") from exc
    if result is sympy.S.Reals:
        return {"status": "infinite", "solution": "(-oo, oo)"}
    if result is sympy.S.EmptySet:
        raise errors.no_solution("inequality has no solution")
    return {"status": "exact", "solution": str(result)}


def limit_expr(text: str, variable: str, point: str, direction: str = "both") -> str:
    sympy = _require_sympy()
    var = _symbols(sympy, [variable])[0]
    if direction not in ("both", "left", "right"):
        raise errors.invalid_expression("direction must be both, left, or right")
    try:
        target = parse(point)
        if direction == "both":
            result = sympy.limit(parse(text), var, target)
        else:
            result = sympy.limit(
                parse(text), var, target, dir="-" if direction == "left" else "+"
            )
    except errors.CalculatorError:
        raise
    except Exception as exc:
        raise errors.too_complex(f"limit failed ({exc})") from exc
    if result in (sympy.zoo, sympy.nan):
        raise errors.undefined("limit does not exist")
    return str(result)


def differentiate(text: str, variable: str, order: int = 1) -> str:
    sympy = _require_sympy()
    if order < 1 or order > 10:
        raise errors.invalid_expression("derivative order must be 1-10")
    var = _symbols(sympy, [variable])[0]
    try:
        return str(sympy.diff(parse(text), var, order))
    except errors.CalculatorError:
        raise
    except Exception as exc:
        raise errors.too_complex(f"differentiation failed ({exc})") from exc


def partial_derivatives(text: str, variables: list[str]) -> dict[str, str]:
    sympy = _require_sympy()
    if not variables or len(variables) > 6:
        raise errors.invalid_expression("need 1-6 variables")
    try:
        expr = parse(text)
        return {name: str(sympy.diff(expr, sympy.Symbol(name))) for name in variables}
    except errors.CalculatorError:
        raise
    except Exception as exc:
        raise errors.too_complex(f"partial derivatives failed ({exc})") from exc


def gradient(text: str, variables: list[str]) -> list[str]:
    parts = partial_derivatives(text, variables)
    return [parts[name] for name in variables]


def integrate(
    text: str, variable: str, lower: str | None = None, upper: str | None = None
) -> str:
    sympy = _require_sympy()
    var = _symbols(sympy, [variable])[0]
    try:
        expr = parse(text)
        if lower is None and upper is None:
            return str(sympy.integrate(expr, var))
        if lower is None or upper is None:
            raise errors.invalid_expression("definite integrals need both bounds")
        return str(sympy.integrate(expr, (var, parse(lower), parse(upper))))
    except errors.CalculatorError:
        raise
    except Exception as exc:
        raise errors.too_complex(f"integration failed ({exc})") from exc


def series(text: str, variable: str, point: str = "0", order: int = 6) -> str:
    sympy = _require_sympy()
    if order < 1 or order > 12:
        raise errors.invalid_expression("series order must be 1-12")
    var = _symbols(sympy, [variable])[0]
    try:
        return str(sympy.series(parse(text), var, parse(point), order))
    except errors.CalculatorError:
        raise
    except Exception as exc:
        raise errors.too_complex(f"series expansion failed ({exc})") from exc


def solve_ode(text: str, function: str, variable: str) -> dict:
    """Attempt a symbolic ODE solve; report honestly when unsupported."""
    sympy = _require_sympy()
    if not function.strip().isidentifier():
        raise errors.invalid_expression("bad function name")
    var = _symbols(sympy, [variable])[0]
    undefined = sympy.Function(function.strip())
    func = undefined(var)
    left, right = _split_equation(text)
    from asis.calculator.parser import parse as safe_parse

    extra = {"Derivative": sympy.Derivative, function.strip(): undefined}
    try:
        equation = sympy.Eq(
            safe_parse(left, extra_functions=extra),
            safe_parse(right, extra_functions=extra),
        )
        solution = sympy.dsolve(equation, func)
    except errors.CalculatorError:
        raise
    except Exception as exc:
        raise errors.too_complex(f"ODE solver failed ({exc})") from exc
    if solution is None or solution == []:
        raise errors.no_solution("differential equation has no solution")
    return {"status": "exact", "solutions": [str(solution)]}
