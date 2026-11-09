"""Offline calculator engine: arithmetic through finance, all local.

Deterministic SymPy-backed tests plus security battery (no eval/exec),
property cross-checks, offline isolation, tool/native/CLI/voice paths,
configuration, and performance bounds.
"""

from __future__ import annotations

import math
import socket
import time
from pathlib import Path

import pytest

from asis.ai import AIManager
from asis.ai.providers import MockAIProvider
from asis.ai.tool_schemas import tool_definitions_for
from asis.app import AssistantApp
from asis.app.assistant import build_coding_tool_router, build_default_tool_router
from asis.calculator import CalculatorEngine, CalculatorError
from asis.configuration.settings import load_settings
from asis.errors import ConfigurationError
from asis.identity import build_identity
from asis.permissions.manager import PermissionManager
from asis.permissions.models import PermissionLevel
from asis.tools.executor import ToolExecutor
from asis.tools.provided.calculator_tools import (
    CalculateTool,
    register_calculator_tools,
)
from asis.tools.registry import ToolRegistry
from asis.tools.router import ToolRouter


def _engine(**kw):
    return CalculatorEngine(**kw)


def _calc(expression, **kw):
    return _engine().calculate("calculate", {"expression": expression, **kw})


def _app(memory_manager, provider, router=None, **kw):
    return AssistantApp(
        identity=build_identity(),
        ai=AIManager(provider=provider),
        memory=memory_manager,
        tools_router=router,
        **kw,
    )


def _calc_router(engine=None, authorizer=None):
    registry = ToolRegistry()
    registry.register(CalculateTool(engine))
    return ToolRouter(
        registry,
        ToolExecutor(
            authorizer=authorizer if authorizer is not None else (lambda t: True)
        ),
    )


# -- arithmetic --------------------------------------------------------------


@pytest.mark.parametrize(
    "expression,exact,numeric",
    [
        ("2 + 2", "4", 4.0),
        ("17 * 43", "731", 731.0),
        ("144 / 12", "12", 12.0),
        ("2^10", "1024", 1024.0),
        ("2**10", "1024", 1024.0),
        ("10 % 3", "1", 1.0),
        ("7 // 2", "3", 3.0),
        ("-5 + 3", "-2", -2.0),
        ("-(2 + 3) * 4", "-20", -20.0),
        ("2 + 3 * 4", "14", 14.0),
        ("(2 + 3) * 4", "20", 20.0),
        ("3.5 * 2", "7.00000000000000", 7.0),
        ("6.02e23", "6.02000000000000e+23", 6.02e23),
        ("1e-3", "0.00100000000000000", 0.001),
    ],
)
def test_arithmetic_cases(expression, exact, numeric):
    result = _calc(expression)
    assert result.exact_result == exact
    assert result.numeric_result == numeric
    assert result.verification["match"] is True


def test_exact_rational_arithmetic():
    result = _calc("1/3 + 1/6")
    assert result.exact_result == "1/2"
    assert result.numeric_result == 0.5


def test_division_by_zero_is_undefined():
    with pytest.raises(CalculatorError) as exc:
        _calc("1/0")
    assert exc.value.code == "CALCULATION_UNDEFINED"


# -- scientific --------------------------------------------------------------


@pytest.mark.parametrize(
    "expression,exact",
    [
        ("sqrt(25)", "5"),
        ("sqrt(2)", "sqrt(2)"),
        ("cbrt(27)", "3"),
        ("abs(-7)", "7"),
        ("exp(0)", "1"),
        ("ln(e)", "1"),
        ("log(100, 10)", "2"),
        ("log10(1000)", "3"),
        ("log2(8)", "3"),
        ("factorial(5)", "120"),
        ("floor(3.7)", "3"),
        ("ceil(3.2)", "4"),
        ("gcd(12, 18)", "6"),
        ("lcm(4, 6)", "12"),
    ],
)
def test_scientific_functions(expression, exact):
    assert _calc(expression).exact_result == exact


def test_constants():
    engine = _engine()
    assert engine.calculate("constant", {"name": "pi"}).numeric_result == pytest.approx(
        math.pi
    )
    assert engine.calculate("constant", {"name": "e"}).numeric_result == pytest.approx(
        math.e
    )
    light = engine.calculate("constant", {"name": "c"})
    assert light.numeric_result == pytest.approx(299792458.0)
    assert light.units == "m/s"
    with pytest.raises(CalculatorError) as exc:
        engine.calculate("constant", {"name": "nope"})
    assert exc.value.code == "CALCULATION_INVALID_EXPRESSION"


# -- angles / trig -----------------------------------------------------------


def test_trig_exact_special_angles():
    engine = _engine()
    assert (
        engine.calculate("trig", {"function": "sin", "arguments": "pi/6"}).exact_result
        == "1/2"
    )
    assert (
        engine.calculate("trig", {"function": "cos", "arguments": "pi/3"}).exact_result
        == "1/2"
    )
    assert (
        engine.calculate("trig", {"function": "tan", "arguments": "pi/4"}).exact_result
        == "1"
    )


def test_trig_degree_suffix_and_mode():
    assert _calc("sin(30°)").exact_result == "1/2"
    engine = _engine(angle_mode="degrees")
    assert (
        engine.calculate("trig", {"function": "sin", "arguments": "30"}).exact_result
        == "1/2"
    )
    assert (
        engine.calculate("trig", {"function": "asin", "arguments": "1"}).exact_result
        == "90"
    )
    grad = _engine(angle_mode="gradians")
    assert (
        grad.calculate("trig", {"function": "sin", "arguments": "100"}).exact_result
        == "1"
    )


def test_trig_hyperbolic_and_atan2():
    engine = _engine()
    assert (
        engine.calculate("trig", {"function": "sinh", "arguments": "0"}).exact_result
        == "0"
    )
    assert engine.calculate(
        "trig", {"function": "atan2", "arguments": "1; 1"}
    ).numeric_result == pytest.approx(math.pi / 4)


# -- complex -----------------------------------------------------------------


def test_complex_arithmetic():
    engine = _engine()
    assert (
        engine.calculate(
            "complex", {"function": "abs", "arguments": "3+4*i"}
        ).exact_result
        == "5"
    )
    assert (
        engine.calculate(
            "complex", {"function": "conjugate", "arguments": "2+3*i"}
        ).exact_result
        == "2 - 3*I"
    )
    assert (
        engine.calculate(
            "complex", {"function": "pow", "arguments": "i; 2"}
        ).exact_result
        == "-1"
    )
    polar = engine.calculate("complex", {"function": "polar", "arguments": "1+i"})
    assert polar.exact_result == "(sqrt(2), pi/4)"
    rect = engine.calculate("complex", {"function": "rect", "arguments": "1; pi/2"})
    assert rect.numeric_result is None or isinstance(rect.numeric_result, float)


# -- algebra -----------------------------------------------------------------


def test_algebra_simplify_factor_expand():
    engine = _engine()
    assert (
        engine.calculate("simplify", {"expression": "(x^2 - 1)/(x - 1)"}).exact_result
        == "x + 1"
    )
    assert (
        engine.calculate("factor", {"expression": "x^2 - 5*x + 6"}).exact_result
        == "(x - 3)*(x - 2)"
    )
    assert (
        engine.calculate("expand", {"expression": "(x + 2)^3"}).exact_result
        == "x**3 + 6*x**2 + 12*x + 8"
    )
    assert (
        engine.calculate(
            "collect", {"expression": "x^2 + 2*x*y + x", "variable": "x"}
        ).exact_result
        is not None
    )
    assert (
        engine.calculate(
            "substitute", {"expression": "x^2 + 1", "variable": "x", "value": "3"}
        ).exact_result
        == "10"
    )


def test_factor_verification_marks_match():
    result = _engine().calculate("factor", {"expression": "x^2 - 5*x + 6"})
    assert result.verification == {"method": "expand-and-compare", "match": True}


# -- equations ---------------------------------------------------------------


def test_linear_equation():
    result = _engine().calculate("solve", {"equation": "2*x + 5 = 17", "variable": "x"})
    assert result.exact_result == "6"
    assert result.verification == {"method": "back-substitution", "match": True}


def test_quadratic_equation():
    result = _engine().calculate(
        "solve", {"equation": "x^2 - 5*x + 6 = 0", "variable": "x"}
    )
    assert result.exact_result == "2, 3"
    assert result.steps == ("x = 2", "x = 3")
    assert result.verification["match"] is True


def test_cubic_equation():
    result = _engine().calculate(
        "solve", {"equation": "x^3 - 6*x^2 + 11*x - 6 = 0", "variable": "x"}
    )
    assert result.exact_result == "1, 2, 3"


def test_simultaneous_system():
    result = _engine().calculate(
        "solve_system", {"equations": "x + y = 10; 2*x - y = 5", "variables": "x; y"}
    )
    assert "x = 5" in result.exact_result and "y = 5" in result.exact_result


def test_no_solution_and_infinite():
    engine = _engine()
    with pytest.raises(CalculatorError) as exc:
        engine.calculate("solve", {"equation": "x = x + 1", "variable": "x"})
    assert exc.value.code == "CALCULATION_NO_SOLUTION"
    infinite = engine.calculate("solve", {"equation": "x + 1 = x + 1", "variable": "x"})
    assert "infinitely many" in infinite.exact_result


def test_inequalities():
    engine = _engine()
    assert (
        engine.calculate(
            "inequality", {"expression": "x > 5", "variable": "x"}
        ).exact_result
        == "Interval.open(5, oo)"
    )
    assert (
        engine.calculate(
            "inequality", {"expression": "x^2 - 4 < 0", "variable": "x"}
        ).exact_result
        == "Interval.open(-2, 2)"
    )


# -- calculus ----------------------------------------------------------------


def test_limits():
    engine = _engine()
    assert (
        engine.calculate(
            "limit", {"expression": "sin(x)/x", "variable": "x", "point": "0"}
        ).exact_result
        == "1"
    )


def test_derivatives():
    engine = _engine()
    first = engine.calculate(
        "differentiate", {"expression": "x^3 + 2*x", "variable": "x"}
    )
    assert first.exact_result == "3*x**2 + 2"
    assert first.verification == {"method": "finite-difference", "match": True}
    second = engine.calculate(
        "differentiate", {"expression": "x^3 + 2*x", "variable": "x", "order": "2"}
    )
    assert second.exact_result == "6*x"
    parts = engine.calculate(
        "partial", {"expression": "x^2 + x*y", "variables": "x; y"}
    )
    assert "2*x + y" in parts.exact_result
    grad = engine.calculate(
        "gradient", {"expression": "x^2 + x*y", "variables": "x; y"}
    )
    assert grad.exact_result == "[2*x + y, x]"


def test_integrals_verified():
    engine = _engine()
    indefinite = engine.calculate("integrate", {"expression": "x^2", "variable": "x"})
    assert indefinite.exact_result == "x**3/3"
    definite = engine.calculate(
        "integrate", {"expression": "x^2", "variable": "x", "lower": "0", "upper": "1"}
    )
    assert definite.exact_result == "1/3"
    assert definite.numeric_result == pytest.approx(1 / 3)
    assert definite.verification == {"method": "simpson-quadrature", "match": True}


def test_series_and_ode():
    engine = _engine()
    series = engine.calculate(
        "series", {"expression": "exp(x)", "variable": "x", "point": "0", "order": "4"}
    )
    assert "x**3/6" in series.exact_result
    ode = engine.calculate(
        "ode",
        {
            "equation": "Derivative(f(x), x) + f(x) = 0",
            "function": "f",
            "variable": "x",
        },
    )
    assert "C1*exp(-x)" in ode.exact_result


# -- matrices / vectors ------------------------------------------------------


def test_matrix_multiply_formats_nested():
    result = _engine().calculate(
        "matrix",
        {"detail": "multiply", "matrices": "[[1,2],[3,4]] || [[5,6],[7,8]]"},
    )
    assert result.exact_result == "[[19, 22], [43, 50]]"


def test_matrix_inverse_verified():
    result = _engine().calculate(
        "matrix", {"detail": "inverse", "matrices": "[[1,2],[3,4]]"}
    )
    assert result.exact_result == "[[-2, 1], [3/2, -1/2]]"
    assert result.verification == {
        "method": "A-multiply-inverse-equals-I",
        "match": True,
    }


def test_matrix_determinant_and_system():
    engine = _engine()
    det = engine.calculate(
        "matrix", {"detail": "determinant", "matrices": "[[1,2],[3,4]]"}
    )
    assert det.exact_result == "-2"
    solved = engine.calculate(
        "matrix",
        {"detail": "solve_linear", "matrices": "[[2,1],[1,3]] || [[5],[6]]"},
    )
    assert solved.exact_result == "[[9/5], [7/5]]"


def test_matrix_dimension_errors():
    engine = _engine()
    with pytest.raises(CalculatorError) as exc:
        engine.calculate(
            "matrix", {"detail": "multiply", "matrices": "[[1,2]] || [[1,2]]"}
        )
    assert exc.value.code == "CALCULATION_DIMENSION_ERROR"
    with pytest.raises(CalculatorError) as exc:
        engine.calculate("matrix", {"detail": "inverse", "matrices": "[[1,2],[2,4]]"})
    assert exc.value.code == "CALCULATION_NO_SOLUTION"


def test_matrix_size_limit():
    engine = CalculatorEngine(max_matrix_size=2)
    with pytest.raises(CalculatorError) as exc:
        engine.calculate(
            "matrix", {"detail": "determinant", "matrices": "[[1,2,3],[4,5,6],[7,8,9]]"}
        )
    assert exc.value.code == "CALCULATION_TOO_COMPLEX"


def test_vector_operations():
    engine = _engine()
    assert (
        engine.calculate(
            "vector", {"detail": "dot", "vectors": "[1,2,3] || [4,5,6]"}
        ).exact_result
        == "32"
    )
    assert (
        engine.calculate(
            "vector", {"detail": "cross", "vectors": "[1,0,0] || [0,1,0]"}
        ).exact_result
        == "[[0], [0], [1]]"
    )
    assert (
        engine.calculate(
            "vector", {"detail": "magnitude", "vectors": "[3,4]"}
        ).exact_result
        == "5"
    )
    assert (
        engine.calculate(
            "vector", {"detail": "add", "vectors": "[1,2] || [3,4]"}
        ).exact_result
        == "[[4], [6]]"
    )
    with pytest.raises(CalculatorError) as exc:
        engine.calculate("vector", {"detail": "dot", "vectors": "[1,2] || [1,2,3]"})
    assert exc.value.code == "CALCULATION_DIMENSION_ERROR"


# -- geometry ----------------------------------------------------------------


@pytest.mark.parametrize(
    "shape,params,fragment",
    [
        ("square", {"side": "4"}, "area = 16"),
        ("rectangle", {"length": "3", "width": "4"}, "area = 12"),
        ("triangle", {"base": "4", "height": "3"}, "area = 6"),
        ("triangle", {"a": "3", "b": "4", "c": "5"}, "area = 6"),
        ("circle", {"radius": "1"}, f"area = {math.pi}"),
        ("cube", {"side": "2"}, "volume = 8"),
        ("sphere", {"radius": "1"}, "volume = "),
        ("cylinder", {"radius": "1", "height": "2"}, "volume = "),
        ("cone", {"radius": "1", "height": "3"}, "volume = "),
        ("polygon", {"sides": "6", "length": "2"}, "perimeter = 12"),
    ],
)
def test_geometry_primitives(shape, params, fragment):
    result = _engine().calculate("geometry", {"shape": shape, "params": params})
    assert fragment in result.exact_result


def test_pythagoras_and_heron_triangle():
    engine = _engine()
    assert (
        engine.calculate(
            "triangle", {"params": {"a": "3", "b": "4", "c": "5"}}
        ).exact_result
        is not None
    )
    with pytest.raises(CalculatorError):
        engine.calculate(
            "geometry", {"shape": "triangle", "params": {"a": "1", "b": "2", "c": "10"}}
        )


def test_ambiguous_triangle_reports_both():
    result = _engine().calculate(
        "triangle", {"params": {"a": "5", "b": "7", "A": "30"}}
    )
    assert "solution 1" in result.exact_result and "solution 2" in result.exact_result
    assert "ambiguous" in result.warnings[0]


# -- statistics / probability / number theory --------------------------------


def test_statistics_sample_vs_population():
    engine = _engine()
    sample = engine.calculate(
        "statistics", {"function": "describe", "data": "[1,2,3,4,5]"}
    )
    assert "mean = 3" in sample.exact_result and "variance = 2.5" in sample.exact_result
    population = engine.calculate(
        "statistics", {"function": "describe", "data": "[1,2,3,4,5]", "sample": "false"}
    )
    assert "variance = 2" in population.exact_result
    assert "variance_type = population" in population.exact_result


def test_probability_functions():
    engine = _engine()
    assert (
        engine.calculate(
            "probability", {"function": "combinations", "n": "5", "r": "2"}
        ).exact_result
        == "10"
    )
    assert (
        engine.calculate(
            "probability", {"function": "permutations", "n": "5", "r": "2"}
        ).exact_result
        == "20"
    )
    assert (
        engine.calculate(
            "probability", {"function": "factorial", "n": "5"}
        ).exact_result
        == "120"
    )
    binomial = engine.calculate(
        "probability",
        {"function": "binomial", "trials": "10", "successes": "3", "p": "0.5"},
    )
    assert binomial.numeric_result == pytest.approx(0.1171875)
    bayes = engine.calculate(
        "probability",
        {"function": "bayes", "prior": "0.01", "likelihood": "0.9", "evidence": "0.05"},
    )
    assert bayes.numeric_result == pytest.approx(0.18)
    with pytest.raises(CalculatorError) as exc:
        engine.calculate(
            "probability", {"function": "combinations", "n": "3", "r": "5"}
        )
    assert exc.value.code == "CALCULATION_DOMAIN_ERROR"


def test_number_theory():
    engine = _engine()
    assert (
        engine.calculate(
            "number_theory", {"function": "is_prime", "n": "104729"}
        ).exact_result
        == "True"
    )
    assert (
        engine.calculate(
            "number_theory", {"function": "is_prime", "n": "104730"}
        ).exact_result
        == "False"
    )
    assert (
        engine.calculate(
            "number_theory", {"function": "factor", "n": "360"}
        ).exact_result
        == "2 * 2 * 2 * 3 * 3 * 5"
    )
    assert (
        engine.calculate(
            "number_theory", {"function": "mod_inverse", "a": "3", "modulus": "11"}
        ).exact_result
        == "4"
    )
    assert (
        engine.calculate(
            "number_theory", {"function": "fibonacci", "n": "10"}
        ).exact_result
        == "55"
    )


# -- units / physics / finance -----------------------------------------------


@pytest.mark.parametrize(
    "value,source,target,expected",
    [
        ("10", "km", "mi", 6.2137119223733395),
        ("25", "degC", "degF", 77.0),
        ("100", "psi", "kPa", 689.4757293168),
        ("60", "mph", "kph", 96.56064),
    ],
)
def test_unit_conversions(value, source, target, expected):
    result = _engine().calculate(
        "convert_units", {"value": value, "from": source, "to": target}
    )
    assert result.numeric_result == pytest.approx(expected)
    assert result.units == target
    assert result.verification == {"method": "round-trip conversion", "match": True}


def test_invalid_conversion_rejected():
    with pytest.raises(CalculatorError) as exc:
        _engine().calculate("convert_units", {"value": "5", "from": "kg", "to": "m"})
    assert exc.value.code == "CALCULATION_DIMENSION_ERROR"


def test_physics_formulas():
    engine = _engine()
    force = engine.calculate(
        "physics", {"formula": "force", "params": {"mass": "2", "a": "3"}}
    )
    assert force.numeric_result == 6.0 and force.units == "N"
    ohm = engine.calculate(
        "physics", {"formula": "ohms_law", "params": {"V": "12", "R": "4"}}
    )
    assert ohm.numeric_result == 3.0 and ohm.units == "A"
    kinetic = engine.calculate(
        "physics", {"formula": "kinetic_energy", "params": {"mass": "2", "v": "10"}}
    )
    assert kinetic.numeric_result == 100.0 and kinetic.units == "J"


def test_engineering_and_finance():
    engine = _engine()
    series = engine.calculate(
        "engineering",
        {"calculation": "series_resistance", "params": {"R1": "10", "R2": "20"}},
    )
    assert series.numeric_result == 30.0
    loan = engine.calculate(
        "finance",
        {
            "calculation": "loan_payment",
            "params": {"P": "100000", "r": "0.005", "n": "360"},
        },
    )
    assert loan.numeric_result == pytest.approx(599.5505251527569)
    assert "fixed rate" in loan.steps[1]


# -- security ----------------------------------------------------------------


@pytest.mark.parametrize(
    "evil",
    [
        "__import__('os').system('x')",
        "exec('1+1')",
        "eval('1+1')",
        "open('/etc/passwd').read()",
        "().__class__.__base__",
        "os.system('ls')",
        "import os",
        "[x for x in range(3)]",
        "getattr(x, 'y')",
        "lambda x: x + 1",
        "while True: pass",
        "().__class__.__subclasses__()",
        "a.b + c",
    ],
)
def test_malicious_expressions_fail_safely(evil):
    with pytest.raises(CalculatorError) as exc:
        _engine().calculate("calculate", {"expression": evil})
    assert exc.value.code in (
        "CALCULATION_INVALID_EXPRESSION",
        "CALCULATION_INPUT_TOO_LARGE",
    )


def test_malicious_tool_arguments_fail_safely():
    router = _calc_router(_engine())
    for evil in ("__import__('os')", "exec('x')", "[].__class__"):
        result = router.execute("calculate", operation="calculate", expression=evil)
        assert result.success is False
        assert "CALCULATION_" in result.error


def test_no_eval_exec_in_calculator_package():
    root = Path(__file__).resolve().parent.parent / "asis" / "calculator"
    offenders = []
    for path in sorted(root.rglob("*.py")):
        # re.compile is regex construction, not code evaluation.
        text = path.read_text(encoding="utf-8").replace("re.compile(", "REGEX(")
        for token in (
            "eval(",
            "exec(",
            "compile(",
            "__import__",
            "import os",
            "import sys",
            "import subprocess",
            "import socket",
            "import requests",
        ):
            if token in text:
                offenders.append(f"{path.name}: {token}")
    assert offenders == []


# -- properties / cross-checks ------------------------------------------


def test_addition_commutes():
    engine = _engine()
    left = engine.calculate("calculate", {"expression": "17 + 43"}).exact_result
    right = engine.calculate("calculate", {"expression": "43 + 17"}).exact_result
    assert left == right == "60"


def test_multiply_divide_round_trip():
    engine = _engine()
    value = engine.calculate("calculate", {"expression": "(17 * 43) / 43"}).exact_result
    assert value == "17"


def test_matrix_identity_property():
    engine = _engine()
    result = engine.calculate(
        "matrix",
        {"detail": "multiply", "matrices": "[[1,2],[3,4]] || [[1,0],[0,1]]"},
    )
    assert result.exact_result == "[[1, 2], [3, 4]]"


def test_nonzero_determinant_implies_inverse():
    engine = _engine()
    det = engine.calculate(
        "matrix", {"detail": "determinant", "matrices": "[[2,1],[1,3]]"}
    )
    assert det.exact_result == "5"
    inverse = engine.calculate(
        "matrix", {"detail": "inverse", "matrices": "[[2,1],[1,3]]"}
    )
    assert inverse.verification == {
        "method": "A-multiply-inverse-equals-I",
        "match": True,
    }


def test_unit_round_trip_property():
    engine = _engine()
    there = engine.calculate("convert_units", {"value": "10", "from": "km", "to": "mi"})
    back = engine.calculate(
        "convert_units", {"value": str(there.numeric_result), "from": "mi", "to": "km"}
    )
    assert back.numeric_result == pytest.approx(10.0)


# -- tool / native / modes / voice / CLI -------------------------------------


def test_calculate_tool_registered_both_routers(tmp_path):
    from asis.coding.workspace import CodingWorkspace

    assert "calculate" in build_default_tool_router().registry.list_names()
    coding = build_coding_tool_router(CodingWorkspace(tmp_path.resolve()))
    assert "calculate" in coding.registry.list_names()


def test_calculate_tool_schema():
    registry = ToolRegistry()
    register_calculator_tools(registry, _engine())
    definitions = {d.name: d for d in tool_definitions_for(registry)}
    schema = definitions["calculate"].parameters
    assert schema["required"] == ["operation"]
    assert schema["properties"]["operation"] == {"type": "string"}
    assert schema["properties"]["params"] == {"type": "object"}


def test_calculate_tool_validates_and_disables(monkeypatch):
    import sys as _sys

    tool_router = _calc_router(_engine())
    assert (
        tool_router.execute("calculate", operation="calculate", expression="6*7").data[
            "exact_result"
        ]
        == "42"
    )
    assert tool_router.execute("calculate", operation="frobnicate").success is False
    assert tool_router.execute("calculate").success is False
    module = _sys.modules["asis.configuration.settings"]
    monkeypatch.setattr(
        module, "settings", load_settings({"ASIS_CALCULATOR_ENABLED": "false"})
    )
    denied = tool_router.execute("calculate", operation="calculate", expression="1+1")
    assert denied.success is False
    assert denied.error.startswith("CALCULATION_DISABLED")


def test_calculate_denied_never_executes():
    router = _calc_router(_engine(), authorizer=lambda tool: False)
    result = router.execute("calculate", operation="calculate", expression="6*7")
    assert result.success is False
    assert "denied" in result.error.lower()


def test_native_calculate_call(memory_manager):
    ai = MockAIProvider(
        responses=("", "The answer is 42."),
        tool_sequences=[
            [
                {
                    "name": "calculate",
                    "arguments": {"operation": "calculate", "expression": "6*7"},
                }
            ],
            None,
        ],
    )
    app = _app(memory_manager, ai, router=_calc_router(_engine()))
    assert app.chat("what is 6 times 7") == "The answer is 42."
    blob = " ".join(m.content for m in app.session.messages)
    assert "calculate result" in blob
    assert "'exact_result': '42'" in blob


def test_native_calculate_unknown_operation(memory_manager):
    ai = MockAIProvider(
        responses=("", "cannot do that."),
        tool_sequences=[
            [{"name": "calculate", "arguments": {"operation": "frobnicate"}}],
            None,
        ],
    )
    app = _app(memory_manager, ai, router=_calc_router(_engine()))
    assert app.chat("calculate frob") == "cannot do that."


def test_coding_mode_calculate(memory_manager, tmp_path):
    from asis.coding.workspace import CodingWorkspace

    workspace = CodingWorkspace(tmp_path.resolve())
    ai = MockAIProvider(
        responses=("", "coded math done."),
        tool_sequences=[
            [
                {
                    "name": "calculate",
                    "arguments": {"operation": "calculate", "expression": "2^16"},
                }
            ],
            None,
        ],
    )
    import asis.calculator.engine as engine_module

    real_builder = engine_module.build_engine_from_settings
    engine_module.build_engine_from_settings = lambda settings_obj=None: _engine()
    try:
        app = _app(memory_manager, ai, mode="coding", workspace=workspace)
        assert app.chat("compute 2^16") == "coded math done."
    finally:
        engine_module.build_engine_from_settings = real_builder


def test_voice_calculate_path(memory_manager):
    from asis.voice import (
        MockAudioInput,
        MockAudioOutput,
        MockSpeakerIdentifier,
        MockSpeechRecognizer,
        MockTextToSpeech,
        VoicePipeline,
        VoiceRunner,
        VoiceRunnerConfig,
    )
    from asis.voice.models import AudioData

    ai = MockAIProvider(
        responses=("", "twelve."),
        tool_sequences=[
            [
                {
                    "name": "calculate",
                    "arguments": {"operation": "calculate", "expression": "sqrt(144)"},
                }
            ],
            None,
        ],
    )
    app = _app(memory_manager, ai, router=_calc_router(_engine()))
    tts = MockTextToSpeech()
    pipe = VoicePipeline(
        MockAudioInput([AudioData(samples=[0], sample_rate=16000)]),
        MockSpeechRecognizer(text="what is the square root of 144"),
        MockSpeakerIdentifier(),
        tts,
        MockAudioOutput(),
    )
    summary = VoiceRunner(
        pipe, app, config=VoiceRunnerConfig(require_wake_word=False, max_turns=1)
    ).run()
    assert summary["turns"] == 1
    assert tts.synthesized == ["twelve."]


def test_cli_calculate_single_shot(capsys):
    from asis.cli.calculate import run_calculate

    assert run_calculate(["sqrt(144)"]) == 0
    out = capsys.readouterr().out
    assert "Exact: 12" in out
    assert "Verified" in out


def test_cli_calculate_operations(capsys):
    from asis.cli.calculate import run_calculate

    assert (
        run_calculate(
            [
                "--operation",
                "solve",
                "--equation",
                "x^2 - 5*x + 6 = 0",
                "--variable",
                "x",
            ]
        )
        == 0
    )
    assert "x = 2" in capsys.readouterr().out
    assert run_calculate(["1/0"]) == 2


def test_cli_list_tools_includes_calculate(capsys):
    from asis.cli.main import entry

    assert entry(["--list-tools"]) == 0
    assert "calculate:" in capsys.readouterr().out


# -- offline / config / limits -----------------------------------------------


def test_offline_calculator_works_without_network(monkeypatch):
    def _no_dns(host, port, *args, **kwargs):
        raise socket.gaierror(8, "offline")

    monkeypatch.setattr(socket, "getaddrinfo", _no_dns)
    assert _calc("6*7").exact_result == "42"
    assert (
        _engine()
        .calculate("solve", {"equation": "x^2 - 4 = 0", "variable": "x"})
        .exact_result
        == "-2, 2"
    )


def test_calculator_config_defaults_and_invalid(monkeypatch):
    for name in (
        "ASIS_CALCULATOR_ENABLED",
        "ASIS_CALCULATOR_MAX_EXPRESSION_CHARS",
        "ASIS_CALCULATOR_MAX_MATRIX_SIZE",
        "ASIS_CALCULATOR_TIMEOUT",
        "ASIS_CALCULATOR_PRECISION",
        "ASIS_CALCULATOR_ANGLE_MODE",
    ):
        monkeypatch.delenv(name, raising=False)
    config = load_settings()
    assert config.calculator.enabled is True
    assert config.calculator.max_expression_chars == 2000
    assert config.calculator.max_matrix_size == 10
    assert config.calculator.timeout == 30
    assert config.calculator.precision == 10
    assert config.calculator.angle_mode == "radians"


@pytest.mark.parametrize(
    "env",
    [
        {"ASIS_CALCULATOR_ENABLED": "maybe"},
        {"ASIS_CALCULATOR_MAX_EXPRESSION_CHARS": "10"},
        {"ASIS_CALCULATOR_MAX_MATRIX_SIZE": "1"},
        {"ASIS_CALCULATOR_TIMEOUT": "0"},
        {"ASIS_CALCULATOR_PRECISION": "31"},
        {"ASIS_CALCULATOR_ANGLE_MODE": "turns"},
    ],
)
def test_calculator_invalid_config_rejected(env):
    with pytest.raises(ConfigurationError):
        load_settings(env)


def test_expression_length_limit():
    engine = CalculatorEngine(max_expression_chars=10)
    with pytest.raises(CalculatorError) as exc:
        engine.calculate("calculate", {"expression": "1+2+3+4+5+6+7"})
    assert exc.value.code == "CALCULATION_INPUT_TOO_LARGE"


def test_calculator_permission_is_low():
    tool = CalculateTool(_engine())
    assert tool.permission is PermissionLevel.LOW
    assert PermissionManager().needs_confirmation(tool) is False


# -- performance -------------------------------------------------------------


def test_performance_bounds():
    engine = _engine()
    start = time.monotonic()
    size = 8
    rows = ",".join(
        "[" + ",".join(str(3 if i == j else 1) for j in range(size)) + "]"
        for i in range(size)
    )
    engine.calculate("matrix", {"detail": "inverse", "matrices": f"[{rows}]"})
    data = "[" + ",".join(str(i % 97) for i in range(1000)) + "]"
    engine.calculate("statistics", {"function": "describe", "data": data})
    engine.calculate("solve", {"equation": "x^10 - 1 = 0", "variable": "x"})
    assert time.monotonic() - start < 30
