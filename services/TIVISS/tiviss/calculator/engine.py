"""Calculator engine for T.I.V.I.S.S.

Provides deterministic local mathematics across all engine operations.
Delegates to the local engine -- never to the network, never to the LLM.
"""

from __future__ import annotations

import math
import importlib.util
import re
from dataclasses import dataclass
from typing import Any

from ..configuration import settings as tiviss_settings
from ..errors import ErrorCode, TivissError


@dataclass
class CalculateResult:
    """Structured result of a calculation."""
    operation: str
    expression: str
    exact_result: Any
    numeric_result: float | None
    units: str | None
    variables: list[str]
    steps: list[str]
    verification: str | None
    warnings: list[str]


class CalculationError(TivissError):
    """Calculator-specific error."""
    pass


class CalculatorEngine:
    """Local calculator engine with offline implementation."""

    def __init__(self):
        self._settings = tiviss_settings.calculator

    def calculate(self, operation: str, params: dict[str, Any]) -> CalculateResult:
        """Perform a calculation based on operation type."""
        operation = operation.lower().strip()

        if operation == "evaluate":
            return self._evaluate(params)
        elif operation == "solve":
            return self._solve(params)
        elif operation == "derivative":
            return self._derivative(params)
        elif operation == "integral":
            return self._integral(params)
        elif operation == "matrix":
            return self._matrix(params)
        elif operation == "statistics":
            return self._statistics(params)
        elif operation == "unit":
            return self._unit_conversion(params)
        elif operation == "probability":
            return self._probability(params)
        elif operation == "geometry":
            return self._geometry(params)
        else:
            raise CalculationError(
                ErrorCode.CALCULATION_SYNTAX_ERROR,
                f"Unknown operation: {operation}"
            )

    def _evaluate(self, params: dict[str, Any]) -> CalculateResult:
        """Evaluate a mathematical expression."""
        expression = params.get("expression", "")
        if not expression:
            raise CalculationError(ErrorCode.CALCULATION_SYNTAX_ERROR, "expression is required")

        angle_mode = params.get("angle_mode", self._settings.angle_mode)

        try:
            # Safe evaluation using sympy if available, otherwise basic eval
            if importlib.util.find_spec("sympy") is not None:
                return self._evaluate_sympy(expression, angle_mode)
            else:
                return self._evaluate_basic(expression, angle_mode)
        except Exception as e:
            raise CalculationError(ErrorCode.CALCULATION_SYNTAX_ERROR, f"Evaluation failed: {e}")

    def _evaluate_sympy(self, expression: str, angle_mode: str) -> CalculateResult:
        """Evaluate using sympy for advanced math."""
        import sympy as sp

        # Apply angle mode
        if angle_mode == "degrees":
            # Replace trig functions with degree versions
            expression = re.sub(r'\bsin\b', 'sin_deg', expression)
            expression = re.sub(r'\bcos\b', 'cos_deg', expression)
            expression = re.sub(r'\btan\b', 'tan_deg', expression)
            expression = re.sub(r'\basin\b', 'asin_deg', expression)
            expression = re.sub(r'\bacos\b', 'acos_deg', expression)
            expression = re.sub(r'\batan\b', 'atan_deg', expression)

            # Define degree functions
            sin_deg = lambda x: sp.sin(sp.rad(x))
            cos_deg = lambda x: sp.cos(sp.rad(x))
            tan_deg = lambda x: sp.tan(sp.rad(x))
            asin_deg = lambda x: sp.deg(sp.asin(x))
            acos_deg = lambda x: sp.deg(sp.acos(x))
            atan_deg = lambda x: sp.deg(sp.atan(x))

            local_dict = {
                'sin_deg': sin_deg,
                'cos_deg': cos_deg,
                'tan_deg': tan_deg,
                'asin_deg': asin_deg,
                'acos_deg': acos_deg,
                'atan_deg': atan_deg,
                'pi': sp.pi,
                'e': sp.E,
                'sqrt': sp.sqrt,
                'log': sp.log,
                'exp': sp.exp,
                'abs': abs,
            }
        else:
            local_dict = {
                'sin': sp.sin,
                'cos': sp.cos,
                'tan': sp.tan,
                'asin': sp.asin,
                'acos': sp.acos,
                'atan': sp.atan,
                'sinh': sp.sinh,
                'cosh': sp.cosh,
                'tanh': sp.tanh,
                'pi': sp.pi,
                'e': sp.E,
                'sqrt': sp.sqrt,
                'log': sp.log,
                'exp': sp.exp,
                'abs': abs,
            }

        expr = sp.sympify(expression, locals=local_dict)
        exact = expr
        numeric = float(expr.evalf())

        return CalculateResult(
            operation="evaluate",
            expression=expression,
            exact_result=str(exact),
            numeric_result=numeric,
            units=None,
            variables=list(expr.free_symbols),
            steps=[f"Parsed: {expr}", f"Evaluated: {numeric}"],
            verification=f"Result: {numeric}",
            warnings=[]
        )

    def _evaluate_basic(self, expression: str, angle_mode: str) -> CalculateResult:
        """Basic evaluation without sympy."""
        # Very basic safe evaluation - only for simple arithmetic
        # This is a fallback, real implementation should use sympy
        allowed_names = {
            "pi": math.pi,
            "e": math.e,
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "asin": math.asin,
            "acos": math.acos,
            "atan": math.atan,
            "sinh": math.sinh,
            "cosh": math.cosh,
            "tanh": math.tanh,
            "sqrt": math.sqrt,
            "log": math.log,
            "exp": math.exp,
            "abs": abs,
        }

        if angle_mode == "degrees":
            allowed_names["sin"] = lambda x: math.sin(math.radians(x))
            allowed_names["cos"] = lambda x: math.cos(math.radians(x))
            allowed_names["tan"] = lambda x: math.tan(math.radians(x))
            allowed_names["asin"] = lambda x: math.degrees(math.asin(x))
            allowed_names["acos"] = lambda x: math.degrees(math.acos(x))
            allowed_names["atan"] = lambda x: math.degrees(math.atan(x))

        try:
            result = eval(expression, {"__builtins__": {}}, allowed_names)
            return CalculateResult(
                operation="evaluate",
                expression=expression,
                exact_result=str(result),
                numeric_result=float(result),
                units=None,
                variables=[],
                steps=[f"Evaluated: {expression} = {result}"],
                verification=f"Result: {result}",
                warnings=["Using basic evaluator (sympy not available)"]
            )
        except Exception as e:
            raise CalculationError(ErrorCode.CALCULATION_SYNTAX_ERROR, f"Evaluation failed: {e}")

    def _solve(self, params: dict[str, Any]) -> CalculateResult:
        """Solve an equation."""
        equation = params.get("equation", "")
        variable = params.get("variable", "x")
        if not equation:
            raise CalculationError(ErrorCode.CALCULATION_SYNTAX_ERROR, "equation is required")

        try:
            import sympy as sp
            var = sp.symbols(variable)
            # Parse equation like "x**2 - 4 = 0"
            if "=" in equation:
                left, right = equation.split("=", 1)
                expr = sp.sympify(left.strip()) - sp.sympify(right.strip())
            else:
                expr = sp.sympify(equation)

            solutions = sp.solve(expr, var)
            return CalculateResult(
                operation="solve",
                expression=equation,
                exact_result=[str(s) for s in solutions],
                numeric_result=[float(s.evalf()) if s.is_number else None for s in solutions],
                units=None,
                variables=[variable],
                steps=[f"Equation: {equation}", f"Solutions: {solutions}"],
                verification=f"Solutions: {solutions}",
                warnings=[]
            )
        except ImportError:
            return CalculateResult(
                operation="solve",
                expression=equation,
                exact_result="sympy required for solving",
                numeric_result=None,
                units=None,
                variables=[variable],
                steps=["sympy not available"],
                verification=None,
                warnings=["sympy required for solving equations"]
            )
        except Exception as e:
            raise CalculationError(ErrorCode.CALCULATION_SYNTAX_ERROR, f"Solve failed: {e}")

    def _derivative(self, params: dict[str, Any]) -> CalculateResult:
        """Compute derivative."""
        expression = params.get("expression", "")
        variable = params.get("variable", "x")
        order = int(params.get("order", "1"))

        try:
            import sympy as sp
            var = sp.symbols(variable)
            expr = sp.sympify(expression)
            deriv = sp.diff(expr, var, order)
            return CalculateResult(
                operation="derivative",
                expression=expression,
                exact_result=str(deriv),
                numeric_result=None,
                units=None,
                variables=[variable],
                steps=[f"d^{order}/{variable}^{order} ({expression}) = {deriv}"],
                verification=f"Derivative: {deriv}",
                warnings=[]
            )
        except ImportError:
            raise CalculationError(ErrorCode.CALCULATION_PROVIDER_ERROR, "sympy required for derivatives")
        except Exception as e:
            raise CalculationError(ErrorCode.CALCULATION_SYNTAX_ERROR, f"Derivative failed: {e}")

    def _integral(self, params: dict[str, Any]) -> CalculateResult:
        """Compute integral."""
        expression = params.get("expression", "")
        variable = params.get("variable", "x")
        lower = params.get("lower")
        upper = params.get("upper")

        try:
            import sympy as sp
            var = sp.symbols(variable)
            expr = sp.sympify(expression)
            if lower is not None and upper is not None:
                integral = sp.integrate(expr, (var, lower, upper))
            else:
                integral = sp.integrate(expr, var)
            return CalculateResult(
                operation="integral",
                expression=expression,
                exact_result=str(integral),
                numeric_result=float(integral.evalf()) if hasattr(integral, 'evalf') else None,
                units=None,
                variables=[variable],
                steps=[f"Integral of {expression} = {integral}"],
                verification=f"Integral: {integral}",
                warnings=[]
            )
        except ImportError:
            raise CalculationError(ErrorCode.CALCULATION_PROVIDER_ERROR, "sympy required for integrals")
        except Exception as e:
            raise CalculationError(ErrorCode.CALCULATION_SYNTAX_ERROR, f"Integral failed: {e}")

    def _matrix(self, params: dict[str, Any]) -> CalculateResult:
        """Matrix operations."""
        # Basic matrix operations placeholder
        return CalculateResult(
            operation="matrix",
            expression=str(params),
            exact_result="Matrix operations require numpy/sympy",
            numeric_result=None,
            units=None,
            variables=[],
            steps=["Not fully implemented"],
            verification=None,
            warnings=["Limited matrix support in offline mode"]
        )

    def _statistics(self, params: dict[str, Any]) -> CalculateResult:
        """Statistical calculations."""
        data = params.get("data", [])
        if not data:
            raise CalculationError(ErrorCode.CALCULATION_SYNTAX_ERROR, "data is required")

        try:
            import statistics
            mean_val = statistics.mean(data)
            stdev_val = statistics.stdev(data) if len(data) > 1 else 0
            return CalculateResult(
                operation="statistics",
                expression=f"data={data}",
                exact_result={"mean": mean_val, "stdev": stdev_val, "count": len(data)},
                numeric_result=mean_val,
                units=None,
                variables=[],
                steps=[f"Mean: {mean_val}", f"Stdev: {stdev_val}"],
                verification=f"Mean: {mean_val}",
                warnings=[]
            )
        except Exception as e:
            raise CalculationError(ErrorCode.CALCULATION_SYNTAX_ERROR, f"Statistics failed: {e}")

    def _unit_conversion(self, params: dict[str, Any]) -> CalculateResult:
        """Unit conversions."""
        value = params.get("value")
        from_unit = params.get("from")
        to_unit = params.get("to")

        if value is None or not from_unit or not to_unit:
            raise CalculationError(ErrorCode.CALCULATION_SYNTAX_ERROR, "value, from, and to are required")

        # Basic unit conversions
        conversions = {
            ("m", "ft"): 3.28084,
            ("ft", "m"): 0.3048,
            ("kg", "lb"): 2.20462,
            ("lb", "kg"): 0.453592,
            ("c", "f"): lambda c: c * 9/5 + 32,
            ("f", "c"): lambda f: (f - 32) * 5/9,
        }

        key = (from_unit.lower(), to_unit.lower())
        if key in conversions:
            if callable(conversions[key]):
                result = conversions[key](value)
            else:
                result = value * conversions[key]
        else:
            raise CalculationError(ErrorCode.CALCULATION_SYNTAX_ERROR, f"Unknown conversion: {from_unit} -> {to_unit}")

        return CalculateResult(
            operation="unit",
            expression=f"{value} {from_unit} -> {to_unit}",
            exact_result=result,
            numeric_result=float(result),
            units=to_unit,
            variables=[],
            steps=[f"{value} {from_unit} = {result} {to_unit}"],
            verification=f"Converted: {result} {to_unit}",
            warnings=[]
        )

    def _probability(self, params: dict[str, Any]) -> CalculateResult:
        """Probability calculations."""
        return CalculateResult(
            operation="probability",
            expression=str(params),
            exact_result="Probability operations require scipy",
            numeric_result=None,
            units=None,
            variables=[],
            steps=["Not fully implemented"],
            verification=None,
            warnings=["Limited probability support in offline mode"]
        )

    def _geometry(self, params: dict[str, Any]) -> CalculateResult:
        """Geometry calculations."""
        shape = params.get("shape", "")
        return CalculateResult(
            operation="geometry",
            expression=str(params),
            exact_result=f"Geometry: {shape} not fully implemented",
            numeric_result=None,
            units=None,
            variables=[],
            steps=["Not fully implemented"],
            verification=None,
            warnings=["Limited geometry support in offline mode"]
        )


def build_engine_from_settings() -> CalculatorEngine:
    """Build calculator engine from settings."""
    return CalculatorEngine()