"""Calculator operations: pure per-operation implementations.

Split out of engine.py with zero behavior change. Each operation takes
an explicit :class:`OpContext` (limits, precision, angle mode) instead of
engine private state; dispatch lives in :class:`CalculatorEngine`.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from asis.calculator import errors
from asis.calculator.formatting import format_exact, format_number
from asis.calculator.models import CalculatorResult
from asis.calculator.validation import check_expression


@dataclass(frozen=True)
class OpContext:
    """Explicit per-call engine settings (replaces private attributes)."""

    max_chars: int
    max_matrix: int
    precision: int
    angle_mode: str


OPERATIONS = (
    "calculate",
    "simplify",
    "expand",
    "factor",
    "collect",
    "substitute",
    "solve",
    "solve_system",
    "inequality",
    "differentiate",
    "partial",
    "gradient",
    "integrate",
    "limit",
    "series",
    "ode",
    "trig",
    "complex",
    "matrix",
    "vector",
    "geometry",
    "triangle",
    "statistics",
    "probability",
    "number_theory",
    "convert_units",
    "constant",
    "physics",
    "engineering",
    "finance",
)

DEFAULT_PRECISION = 10


def _expression(ctx, text: str) -> str:
    return check_expression(text, max_chars=ctx.max_chars)

def _dataset(ctx, raw) -> str:
    # Datasets never reach the symbolic parser (plain float split),
    # so they validate under a larger linear-time budget.
    from asis.calculator.validation import check_expression as check

    text = raw if isinstance(raw, str) else str(raw or "")
    return check(text, max_chars=100_000)

def _result(ctx,
    operation: str,
    expression: str,
    *,
    exact=None,
    numeric=None,
    units=None,
    variables=(),
    steps=(),
    verification=None,
    warnings=(),
) -> CalculatorResult:
    exact_text = format_exact(exact) if exact is not None else None
    number = None
    if numeric is not None:
        try:
            number = format_number(float(numeric), precision=ctx.precision)
        except (TypeError, ValueError):
            number = None
    return CalculatorResult(
        operation=operation,
        expression=expression,
        exact_result=exact_text,
        numeric_result=number,
        units=units,
        variables=tuple(variables),
        steps=tuple(steps),
        verification=verification,
        warnings=tuple(warnings),
    )


# -- arithmetic / scientific -------------------------------------------
def _op_calculate(ctx, args: dict) -> CalculatorResult:
    from asis.calculator.evaluator import evaluate

    expression = _expression(ctx, args.get("expression", ""))
    angle = str(args.get("angle_mode", ctx.angle_mode))
    exact, numeric = evaluate(expression, angle_mode=angle)
    verification = _verify_numeric(ctx, expression, numeric, angle)
    return _result(ctx,
        "calculate",
        expression,
        exact=exact,
        numeric=numeric,
        verification=verification,
    )

def _verify_numeric(ctx, expression: str, numeric, angle: str) -> dict | None:
    """Independent re-evaluation via code generation (separate path).

    The already-parsed SymPy object (never the raw string) is compiled
    through ``lambdify`` against the plain ``math`` module — a different
    evaluation route from the symbolic simplifier, with no eval/exec
    of user input anywhere in the package.
    """
    if numeric is None:
        return None
    try:
        import sympy

        from asis.calculator.parser import parse

        expr = parse(expression)
        if expr.free_symbols:
            return None
        value = float(sympy.lambdify((), expr, "math")())
        if not math.isfinite(value):
            return {"method": "independent float re-evaluation", "match": None}
        match = math.isclose(value, float(numeric), rel_tol=1e-9, abs_tol=1e-12)
        return {"method": "independent float re-evaluation", "match": bool(match)}
    except Exception:
        return {"method": "independent float re-evaluation", "match": None}

def _op_trig(ctx, args: dict) -> CalculatorResult:
    from asis.calculator.evaluator import trig

    name = str(args.get("function", "")).strip().lower()
    raw_args = args.get("arguments", "")
    if isinstance(raw_args, str):
        items = [part.strip() for part in raw_args.split(";") if part.strip()]
    else:
        items = [str(item) for item in (raw_args or [])]
    for item in items:
        _expression(ctx, item)
    angle = str(args.get("angle_mode", ctx.angle_mode))
    exact, numeric = trig(name, items, angle_mode=angle)
    return _result(ctx,
        "trig",
        f"{name}({', '.join(items)})",
        exact=exact,
        numeric=numeric,
    )

def _op_complex(ctx, args: dict) -> CalculatorResult:
    from asis.calculator.evaluator import complex_op

    name = str(args.get("function", "")).strip().lower()
    raw_args = args.get("arguments", "")
    if isinstance(raw_args, str):
        items = [part.strip() for part in raw_args.split(";") if part.strip()]
    else:
        items = [str(item) for item in (raw_args or [])]
    for item in items:
        _expression(ctx, item)
    exact, numeric = complex_op(name, items)
    return _result(ctx,
        "complex",
        f"{name}({', '.join(items)})",
        exact=exact,
        numeric=numeric,
    )

def _op_constant(ctx, args: dict) -> CalculatorResult:
    from asis.calculator.constants import constant_value
    from asis.calculator.evaluator import evaluate

    name = str(args.get("name", "")).strip()
    if not name:
        raise errors.invalid_expression("constant needs a name")
    value_expr, unit, description = constant_value(name)
    exact, numeric = evaluate(value_expr)
    return _result(ctx,
        "constant",
        name,
        exact=exact,
        numeric=numeric,
        units=unit,
        steps=(description,),
    )

# -- symbolic -----------------------------------------------------------
def _op_simplify(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import symbolic

    expression = _expression(ctx, args.get("expression", ""))
    result = symbolic.simplify_expr(expression)
    return _result(ctx, "simplify", expression, exact=result)

def _op_expand(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import symbolic

    expression = _expression(ctx, args.get("expression", ""))
    return _result(ctx,
        "expand", expression, exact=symbolic.expand_expr(expression)
    )

def _op_factor(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import symbolic

    expression = _expression(ctx, args.get("expression", ""))
    factored = symbolic.factor_expr(expression)
    verification = _verify_factor(ctx, expression, factored)
    return _result(ctx,
        "factor", expression, exact=factored, verification=verification
    )

def _verify_factor(ctx, expression: str, factored: str) -> dict | None:
    try:
        from asis.calculator.parser import parse

        same = bool(
            (
                parse(f"({expression}) - ({factored})").simplify()
                if hasattr(parse(expression), "simplify")
                else None
            )
            == 0
        )
    except Exception:
        return {"method": "expand-and-compare", "match": None}
    try:
        import sympy

        same = sympy.simplify(parse(expression) - parse(factored)) == 0
        return {"method": "expand-and-compare", "match": bool(same)}
    except Exception:
        return {"method": "expand-and-compare", "match": None}

def _op_collect(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import symbolic

    expression = _expression(ctx, args.get("expression", ""))
    variable = str(args.get("variable", "")).strip()
    if not variable:
        raise errors.invalid_expression("collect needs a variable")
    return _result(ctx,
        "collect",
        expression,
        exact=symbolic.collect_expr(expression, variable),
        variables=(variable,),
    )

def _op_substitute(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import symbolic

    expression = _expression(ctx, args.get("expression", ""))
    variable = str(args.get("variable", "")).strip()
    value = _expression(ctx, args.get("value", ""))
    if not variable:
        raise errors.invalid_expression("substitute needs a variable")
    return _result(ctx,
        "substitute",
        expression,
        exact=symbolic.substitute(expression, variable, value),
        variables=(variable,),
    )

def _op_solve(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import symbolic

    equation = _expression(ctx, args.get("equation", ""))
    variable = str(args.get("variable", "x")).strip() or "x"
    outcome = symbolic.solve_equation(equation, variable)
    verification = _verify_solutions(ctx, equation, variable, outcome)
    if outcome["status"] == "infinite":
        return _result(ctx,
            "solve",
            equation,
            exact="infinitely many solutions",
            variables=(variable,),
            verification=verification,
            warnings=("identity equation: every value solves it",),
        )
    solutions = outcome["solutions"]
    numeric = _solution_numeric(ctx, solutions)
    return _result(ctx,
        "solve",
        equation,
        exact=", ".join(solutions),
        numeric=numeric,
        variables=(variable,),
        steps=tuple(f"{variable} = {item}" for item in solutions),
        verification=verification,
    )

def _solution_numeric(ctx, solutions: list) -> float | None:
    if len(solutions) != 1:
        return None
    try:
        from asis.calculator.parser import parse_number

        return parse_number(solutions[0])
    except errors.CalculatorError:
        return None

def _verify_solutions(ctx, equation: str, variable: str, outcome: dict
) -> dict | None:
    """Substitute each solution back into the equation independently."""
    if outcome.get("status") != "exact":
        return None
    try:
        from asis.calculator.parser import parse

        left_text, right_text = equation.split("=", 1)
        left, right = parse(left_text.strip()), parse(right_text.strip())
        import sympy

        checked = []
        for item in outcome["solutions"]:
            value = parse(item)
            residual = complex(
                sympy.N(left.subs(variable, value) - right.subs(variable, value))
            )
            checked.append(abs(residual) < 1e-9)
        return {"method": "back-substitution", "match": bool(all(checked))}
    except Exception:
        return {"method": "back-substitution", "match": None}

def _op_solve_system(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import symbolic

    raw_equations = args.get("equations", "")
    raw_variables = args.get("variables", "")
    equations = _split_list(raw_equations, "equations")
    variables = _split_list(raw_variables, "variables")
    equations = [_expression(ctx, item) for item in equations]
    outcome = symbolic.solve_system(equations, variables)
    if outcome["status"] == "infinite":
        return _result(ctx,
            "solve_system",
            "; ".join(equations),
            exact="infinitely many solutions",
            variables=tuple(variables),
        )
    steps = tuple(
        ", ".join(f"{key} = {value}" for key, value in entry.items())
        for entry in outcome["solutions"]
    )
    return _result(ctx,
        "solve_system",
        "; ".join(equations),
        exact="; ".join(steps),
        variables=tuple(variables),
        steps=steps,
    )

@staticmethod
def _split_list(raw, name: str) -> list[str]:
    if isinstance(raw, str):
        items = [part.strip() for part in raw.split(";") if part.strip()]
    else:
        items = [str(item).strip() for item in (raw or []) if str(item).strip()]
    if not items:
        raise errors.invalid_expression(f"{name} must not be empty")
    return items

def _op_inequality(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import symbolic

    expression = _expression(ctx, args.get("expression", ""))
    variable = str(args.get("variable", "x")).strip() or "x"
    outcome = symbolic.solve_inequality(expression, variable)
    if outcome["status"] == "infinite":
        return _result(ctx,
            "inequality",
            expression,
            exact="(-oo, oo)",
            variables=(variable,),
        )
    return _result(ctx,
        "inequality",
        expression,
        exact=outcome["solution"],
        variables=(variable,),
    )

def _op_differentiate(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import symbolic

    expression = _expression(ctx, args.get("expression", ""))
    variable = str(args.get("variable", "x")).strip() or "x"
    try:
        order = int(str(args.get("order", "1")))
    except ValueError as exc:
        raise errors.invalid_expression("order must be an integer") from exc
    result = symbolic.differentiate(expression, variable, order)
    verification = _verify_derivative(ctx, expression, variable, result)
    return _result(ctx,
        "differentiate",
        expression,
        exact=result,
        variables=(variable,),
        verification=verification,
    )

def _verify_derivative(ctx, expression: str, variable: str, result: str
) -> dict | None:
    """Compare the symbolic derivative against finite differences."""
    try:
        import sympy

        from asis.calculator.parser import parse

        func = sympy.lambdify(variable, parse(expression), "math")
        derived = sympy.lambdify(variable, parse(result), "math")
        points = (0.5, 1.5, 2.5)
        matches = []
        for point in points:
            try:
                expected = (func(point + 1e-6) - func(point - 1e-6)) / 2e-6
                matches.append(
                    math.isclose(
                        float(derived(point)), float(expected), rel_tol=1e-4
                    )
                )
            except Exception:
                return {"method": "finite-difference", "match": None}
        return {"method": "finite-difference", "match": bool(all(matches))}
    except Exception:
        return {"method": "finite-difference", "match": None}

def _op_partial(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import symbolic

    expression = _expression(ctx, args.get("expression", ""))
    variables = _split_list(args.get("variables", ""), "variables")
    parts = symbolic.partial_derivatives(expression, variables)
    steps = tuple(f"d/d{name} = {value}" for name, value in parts.items())
    return _result(ctx,
        "partial",
        expression,
        exact="; ".join(steps),
        variables=tuple(variables),
        steps=steps,
    )

def _op_gradient(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import symbolic

    expression = _expression(ctx, args.get("expression", ""))
    variables = _split_list(args.get("variables", ""), "variables")
    values = symbolic.gradient(expression, variables)
    return _result(ctx,
        "gradient",
        expression,
        exact=f"[{', '.join(values)}]",
        variables=tuple(variables),
    )

def _op_integrate(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import symbolic

    expression = _expression(ctx, args.get("expression", ""))
    variable = str(args.get("variable", "x")).strip() or "x"
    lower = args.get("lower")
    upper = args.get("upper")
    lower_text = _expression(ctx, str(lower)) if lower not in (None, "") else None
    upper_text = _expression(ctx, str(upper)) if upper not in (None, "") else None
    result = symbolic.integrate(expression, variable, lower_text, upper_text)
    verification = None
    if lower_text is not None:
        verification = _verify_definite_integral(ctx,
            expression, variable, lower_text, upper_text, result
        )
    numeric = _solution_numeric(ctx, [result]) if lower_text else None
    return _result(ctx,
        "integrate",
        expression,
        exact=result,
        numeric=numeric,
        variables=(variable,),
        verification=verification,
    )

def _verify_definite_integral(ctx,
    expression: str,
    variable: str,
    lower: str,
    upper: str,
    result: str,
) -> dict | None:
    """Compare against Simpson-rule quadrature independently."""
    try:
        import sympy

        from asis.calculator.parser import parse, parse_number

        func = sympy.lambdify(variable, parse(expression), "math")
        low, high = float(parse_number(lower)), float(parse_number(upper))
        steps = 2000
        width = (high - low) / steps
        total = float(func(low)) + float(func(high))
        for index in range(1, steps):
            weight = 4 if index % 2 else 2
            total += weight * float(func(low + index * width))
        quadrature = total * width / 3
        expected = float(parse_number(result))
        return {
            "method": "simpson-quadrature",
            "match": bool(math.isclose(quadrature, expected, rel_tol=1e-4)),
        }
    except Exception:
        return {"method": "simpson-quadrature", "match": None}

def _op_limit(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import symbolic

    expression = _expression(ctx, args.get("expression", ""))
    variable = str(args.get("variable", "x")).strip() or "x"
    point = _expression(ctx, args.get("point", "0"))
    direction = str(args.get("direction", "both")).strip() or "both"
    result = symbolic.limit_expr(expression, variable, point, direction)
    numeric = _solution_numeric(ctx, [result])
    return _result(ctx,
        "limit",
        expression,
        exact=result,
        numeric=numeric,
        variables=(variable,),
    )

def _op_series(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import symbolic

    expression = _expression(ctx, args.get("expression", ""))
    variable = str(args.get("variable", "x")).strip() or "x"
    point = _expression(ctx, args.get("point", "0"))
    try:
        order = int(str(args.get("order", "6")))
    except ValueError as exc:
        raise errors.invalid_expression("order must be an integer") from exc
    return _result(ctx,
        "series",
        expression,
        exact=symbolic.series(expression, variable, point, order),
        variables=(variable,),
    )

def _op_ode(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import symbolic

    equation = _expression(ctx, args.get("equation", ""))
    function = str(args.get("function", "f")).strip() or "f"
    variable = str(args.get("variable", "x")).strip() or "x"
    outcome = symbolic.solve_ode(equation, function, variable)
    return _result(ctx,
        "ode",
        equation,
        exact="; ".join(outcome["solutions"]),
        variables=(variable,),
    )

# -- linear algebra -------------------------------------------------------
def _op_matrix(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import linalg

    name = str(args.get("detail", args.get("operation", ""))).strip().lower()
    raw = args.get("matrices", "")
    if isinstance(raw, str):
        items = [part.strip() for part in raw.split("||") if part.strip()]
    else:
        items = [str(item) for item in (raw or [])]
    for item in items:
        _expression(ctx, item)
    outcome = linalg.matrix_op(name, items, max_size=ctx.max_matrix)
    verification = None
    if name == "inverse" and items:
        verification = _verify_inverse(ctx, items[0], outcome.get("result", ""))
    numeric = outcome.get("numeric")
    return _result(ctx,
        "matrix",
        " || ".join(items),
        exact=outcome.get("result"),
        numeric=numeric,
        verification=verification,
    )

def _verify_inverse(ctx, original: str, inverted: str) -> dict | None:
    """Check A·A⁻¹ = I independently."""
    try:
        import sympy

        from asis.calculator import linalg

        left = linalg.parse_matrix(original, max_size=ctx.max_matrix)
        right = linalg.parse_matrix(inverted, max_size=ctx.max_matrix)
        product = left * right
        identity = sympy.eye(left.rows)
        match = bool(sympy.simplify(product - identity).is_zero_matrix)
        return {"method": "A-multiply-inverse-equals-I", "match": match}
    except Exception:
        return {"method": "A-multiply-inverse-equals-I", "match": None}

def _op_vector(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import linalg

    name = str(args.get("detail", args.get("operation", ""))).strip().lower()
    raw = args.get("vectors", "")
    if isinstance(raw, str):
        items = [part.strip() for part in raw.split("||") if part.strip()]
    else:
        items = [str(item) for item in (raw or [])]
    for item in items:
        _expression(ctx, item)
    outcome = linalg.vector_op(name, items, max_size=ctx.max_matrix)
    return _result(ctx,
        "vector",
        " || ".join(items),
        exact=outcome.get("result"),
        numeric=outcome.get("numeric"),
    )

# -- geometry ---------------------------------------------------------------
def _op_geometry(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import geometry

    shape = str(args.get("shape", "")).strip()
    if not shape:
        raise errors.invalid_expression("geometry needs a shape")
    params = {
        str(key): str(value)
        for key, value in dict(args.get("params", {}) or {}).items()
    }
    for value in params.values():
        _expression(ctx, value)
    outcome = geometry.geometry(shape, params)
    exact = ", ".join(
        f"{key} = {value}" for key, value in outcome.items() if key != "shape"
    )
    return _result(ctx, "geometry", shape, exact=exact)

def _op_triangle(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import geometry

    params = {
        str(key): str(value)
        for key, value in dict(args.get("params", {}) or {}).items()
    }
    for value in params.values():
        _expression(ctx, value)
    outcome = geometry.triangle_solve(params)
    steps = tuple(
        f"solution {index + 1}: "
        + ", ".join(f"{key} = {round(value, 6)}" for key, value in entry.items())
        for index, entry in enumerate(outcome["solutions"])
    )
    warnings = (
        ("ambiguous SSA case: multiple valid solutions",)
        if outcome.get("ambiguous")
        else ()
    )
    return _result(ctx,
        "triangle",
        ", ".join(f"{k}={v}" for k, v in params.items()),
        exact=" | ".join(steps),
        steps=steps,
        warnings=warnings,
    )

# -- statistics / probability / number theory ----------------------------------
def _op_statistics(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import stats

    name = str(args.get("function", "")).strip().lower()
    data = _dataset(ctx, args.get("data", ""))
    sample = str(args.get("sample", "true")).strip().lower() not in (
        "false",
        "0",
        "no",
    )
    if name == "describe":
        outcome = stats.describe(data, sample=sample)
        exact = ", ".join(f"{key} = {value}" for key, value in outcome.items())
        return _result(ctx, "statistics", data, exact=exact)
    if name == "weighted_mean":
        weights = _dataset(ctx, args.get("weights", ""))
        value = stats.weighted_mean(data, weights)
        return _result(ctx, "statistics", data, exact=str(value), numeric=value)
    if name == "percentile":
        percent = _expression(ctx, args.get("percent", ""))
        value = stats.percentile(data, percent)
        return _result(ctx, "statistics", data, exact=str(value), numeric=value)
    if name == "covariance":
        other = _dataset(ctx, args.get("other", ""))
        value = stats.covariance(data, other, sample=sample)
        return _result(ctx, "statistics", data, exact=str(value), numeric=value)
    if name == "correlation":
        other = _dataset(ctx, args.get("other", ""))
        value = stats.correlation(data, other)
        return _result(ctx, "statistics", data, exact=str(value), numeric=value)
    raise errors.invalid_expression(f"unknown statistics function '{name}'")

def _op_probability(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import stats

    name = str(args.get("function", "")).strip().lower()

    def get(key):
        return _expression(ctx, args.get(key, ""))

    if name == "factorial":
        value = stats.factorial_of(get("n"))
        return _result(ctx,
            "probability", get("n"), exact=str(value), numeric=float(value)
        )
    if name == "permutations":
        value = stats.permutations(get("n"), get("r"))
        return _result(ctx,
            "probability",
            f"n={get('n')}, r={get('r')}",
            exact=str(value),
            numeric=float(value),
        )
    if name == "combinations":
        value = stats.combinations(get("n"), get("r"))
        return _result(ctx,
            "probability",
            f"n={get('n')}, r={get('r')}",
            exact=str(value),
            numeric=float(value),
        )
    if name == "binomial":
        value = stats.binomial_probability(
            get("trials"), get("successes"), get("p")
        )
        return _result(ctx,
            "probability", "binomial", exact=str(value), numeric=value
        )
    if name == "bayes":
        value = stats.bayes(get("prior"), get("likelihood"), get("evidence"))
        return _result(ctx, "probability", "bayes", exact=str(value), numeric=value)
    if name == "expected_value":
        value = stats.expected_value(
            _dataset(ctx, args.get("values", "")),
            _dataset(ctx, args.get("probs", "")),
        )
        return _result(ctx,
            "probability", "expected value", exact=str(value), numeric=value
        )
    raise errors.invalid_expression(f"unknown probability function '{name}'")

def _op_number_theory(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import stats

    name = str(args.get("function", "")).strip().lower()

    def get(key):
        return _expression(ctx, args.get(key, ""))

    if name == "is_prime":
        value = stats.is_prime(get("n"))
        return _result(ctx, "number_theory", get("n"), exact=str(value))
    if name == "factor":
        factors = stats.prime_factors(get("n"))
        return _result(ctx,
            "number_theory",
            get("n"),
            exact=" * ".join(str(item) for item in factors),
            steps=(f"factors: {factors}",),
        )
    if name == "gcd":
        values = _split_list(get("values"), "values")
        result = stats.gcd_of(*values)
        return _result(ctx,
            "number_theory",
            ", ".join(values),
            exact=str(result),
            numeric=float(result),
        )
    if name == "lcm":
        values = _split_list(get("values"), "values")
        result = stats.lcm_of(*values)
        return _result(ctx,
            "number_theory",
            ", ".join(values),
            exact=str(result),
            numeric=float(result),
        )
    if name == "mod_pow":
        result = stats.mod_pow(get("base"), get("exponent"), get("modulus"))
        return _result(ctx,
            "number_theory",
            "modular exponentiation",
            exact=str(result),
            numeric=float(result),
        )
    if name == "mod_inverse":
        result = stats.mod_inverse(get("a"), get("modulus"))
        return _result(ctx,
            "number_theory",
            "modular inverse",
            exact=str(result),
            numeric=float(result),
        )
    if name == "fibonacci":
        result = stats.fibonacci(get("n"))
        return _result(ctx, "number_theory", f"fib({get('n')})", exact=str(result))
    if name == "divisors":
        found = stats.divisors(get("n"))
        return _result(ctx,
            "number_theory",
            get("n"),
            exact=", ".join(str(item) for item in found),
        )
    raise errors.invalid_expression(f"unknown number theory function '{name}'")

# -- units / applied -----------------------------------------------------------
def _op_convert_units(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import units

    value = _expression(ctx, args.get("value", ""))
    source = str(args.get("from", "")).strip()
    target = str(args.get("to", "")).strip()
    if not source or not target:
        raise errors.invalid_expression("convert_units needs value, from, to")
    outcome = units.convert(value, source, target)
    verification = _verify_round_trip(ctx,
        outcome["result"], outcome["to"], value, outcome["from"]
    )
    return _result(ctx,
        "convert_units",
        f"{value} {source} to {target}",
        exact=str(outcome["result"]),
        numeric=outcome["result"],
        units=target,
        verification=verification,
    )

def _verify_round_trip(ctx, value, unit, original_text: str, original_unit: str
) -> dict | None:
    """Convert back and compare with the original value."""
    try:
        from asis.calculator import units
        from asis.calculator.parser import parse_number

        back = units.convert(str(value), unit, original_unit)["result"]
        expected = parse_number(original_text)
        return {
            "method": "round-trip conversion",
            "match": bool(math.isclose(back, expected, rel_tol=1e-9)),
        }
    except Exception:
        return {"method": "round-trip conversion", "match": None}

def _applied_params(ctx, args: dict) -> dict[str, str]:
    params = dict(args.get("params", {}) or {})
    cleaned = {
        str(key): _expression(ctx, str(value)) for key, value in params.items()
    }
    return cleaned

def _op_physics(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import applied

    formula = str(args.get("formula", "")).strip()
    if not formula:
        raise errors.invalid_expression("physics needs a formula")
    outcome = applied.physics(formula, _applied_params(ctx, args))
    return _result(ctx,
        "physics",
        formula,
        exact=str(outcome["result"]),
        numeric=outcome["result"],
        units=outcome.get("unit"),
        steps=(outcome.get("formula", ""),),
    )

def _op_engineering(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import applied

    name = str(args.get("calculation", "")).strip()
    if not name:
        raise errors.invalid_expression("engineering needs a calculation")
    outcome = applied.engineering(name, _applied_params(ctx, args))
    return _result(ctx,
        "engineering",
        name,
        exact=str(outcome["result"]),
        numeric=outcome["result"],
        units=outcome.get("unit"),
        steps=(outcome.get("formula", ""),),
    )

def _op_finance(ctx, args: dict) -> CalculatorResult:
    from asis.calculator import applied

    name = str(args.get("calculation", "")).strip()
    if not name:
        raise errors.invalid_expression("finance needs a calculation")
    outcome = applied.finance(name, _applied_params(ctx, args))
    steps = tuple(
        part
        for part in (outcome.get("formula", ""), outcome.get("assumptions", ""))
        if part
    )
    return _result(ctx,
        "finance",
        name,
        exact=str(outcome["result"]),
        numeric=outcome["result"],
        units=outcome.get("unit"),
        steps=steps,
    )




OPERATION_HANDLERS: dict[str, Callable[[OpContext, dict], CalculatorResult]] = {
    name: globals()[f"_op_{name}"] for name in OPERATIONS
}
