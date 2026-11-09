"""Calculator tool for T.I.V.I.S.S.: calculate.

Delegates to the local CalculatorEngine -- never to the network, never
to the LLM for arithmetic. Results are structured data for the model
to explain, never instructions.
"""

from __future__ import annotations

from typing import Any

from ..configuration import settings as tiviss_settings
from ..permissions.permissions import Permission
from .interface import Tool, ToolError, ToolResult, ToolStatus


# Optional string arguments accepted per operation (all scalar-schema).
_STRING_ARGS = (
    "expression",
    "equation",
    "equations",
    "variables",
    "variable",
    "function",
    "arguments",
    "value",
    "from_unit",
    "to_unit",
    "data",
    "weights",
    "other",
    "percent",
    "point",
    "lower",
    "upper",
    "order",
    "direction",
    "shape",
    "formula",
    "calculation",
    "operation_detail",
    "angle_mode",
    "name",
    "n",
    "r",
    "p",
    "trials",
    "successes",
    "prior",
    "likelihood",
    "evidence",
    "values",
    "probs",
    "base",
    "exponent",
    "modulus",
    "a",
    "matrices",
    "vectors",
)


def _calculator_settings():
    return tiviss_settings.calculator


class CalculateTool(Tool):
    """Deterministic local mathematics across all engine operations."""

    @property
    def tool_id(self) -> str:
        return "calculate"

    @property
    def name(self) -> str:
        return "Calculate"

    @property
    def description(self) -> str:
        return (
            "Exact local math: arithmetic, algebra, calculus, matrices, "
            "statistics, units. Returns exact and numeric results."
        )

    @property
    def permission(self) -> Permission:
        return Permission.of("tools.calculator")

    def __init__(self, engine=None) -> None:
        self._engine = engine

    def _client(self):
        if self._engine is not None:
            return self._engine
        from tiviss.calculator.engine import build_engine_from_settings

        return build_engine_from_settings()

    def validate_input(self, params: dict[str, Any]) -> dict[str, Any]:
        if "operation" not in params:
            raise ToolError("operation must be provided")
        operation = params.get("operation", "")
        if not isinstance(operation, str) or not operation.strip():
            raise ToolError("operation must be a non-empty string")

        validated: dict[str, Any] = {"operation": operation.strip()}
        for key in _STRING_ARGS:
            if key in params and params[key] not in (None, ""):
                value = params[key]
                if not isinstance(value, str):
                    raise ToolError(f"{key} must be a string")
                validated[key] = value
        raw_params = params.get("params")
        if raw_params is not None:
            if not isinstance(raw_params, dict):
                raise ToolError("params must be an object")
            for key, value in raw_params.items():
                validated[str(key)] = value if isinstance(value, str) else str(value)

        # Canonical aliases
        if "operation_detail" in validated:
            validated["detail"] = validated.pop("operation_detail")
        if "from_unit" in validated:
            validated["from"] = validated.pop("from_unit")
        if "to_unit" in validated:
            validated["to"] = validated.pop("to_unit")
        if "from" in params and params["from"] not in (None, ""):
            validated["from"] = str(params["from"])
        if "to" in params and params["to"] not in (None, ""):
            validated["to"] = str(params["to"])
        return validated

    def execute(self, params: dict[str, Any]) -> ToolResult:
        calc_settings = _calculator_settings()
        if not calc_settings.enabled:
            return ToolResult(
                tool_id=self.tool_id,
                status=ToolStatus.FAILED,
                error="CALCULATION_DISABLED: the calculator is disabled by configuration.",
            )

        operation = params.get("operation", "")
        if not isinstance(operation, str) or not operation.strip():
            return ToolResult(
                tool_id=self.tool_id,
                status=ToolStatus.FAILED,
                error="operation must be a non-empty string.",
            )

        validated_params = self.validate_input(params)
        try:
            result = self._client().calculate(validated_params.pop("operation"), validated_params)
        except Exception as exc:
            code = getattr(exc, "code", None)
            message = getattr(exc, "message", None) or str(exc) or "calculation failed"
            if code:
                tail = message.split(": ", 1)[-1] if ": " in message else message
                return ToolResult(
                    tool_id=self.tool_id,
                    status=ToolStatus.FAILED,
                    error=f"{code}: {tail}",
                )
            return ToolResult(
                tool_id=self.tool_id,
                status=ToolStatus.FAILED,
                error=f"CALCULATION_PROVIDER_ERROR: {message}",
            )

        return ToolResult(
            tool_id=self.tool_id,
            status=ToolStatus.OK,
            data={
                "operation": result.operation,
                "expression": result.expression,
                "exact_result": result.exact_result,
                "numeric_result": result.numeric_result,
                "units": result.units,
                "variables": list(result.variables),
                "steps": list(result.steps),
                "verification": result.verification,
                "warnings": list(result.warnings),
            },
        )


def build_calculator_tools(engine=None) -> list[Tool]:
    """Build the calculator tools bound to engine (default if None)."""
    return [CalculateTool(engine)]


def register_calculator_tools(registry, engine=None) -> list[str]:
    """Register calculator tools on registry; returns registered names."""
    names: list[str] = []
    for tool in build_calculator_tools(engine):
        registry.register(tool)
        names.append(tool.tool_id)
    return names