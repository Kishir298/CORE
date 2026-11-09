"""
Calculator tool for A.S.I.S.: ``calculate``.

Travels the standard path (ToolRegistry -> ToolRouter ->
PermissionManager/authorizer -> ToolExecutor) like every other tool and
delegates to the local CalculatorEngine — never to the network, never
to the LLM for arithmetic. Results are structured data for the model
to explain, never instructions.
"""

from __future__ import annotations

from typing import Any

from asis.permissions.models import PermissionLevel

from ..base import Tool, ToolMetadata
from ..result import ToolResult

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
    from asis.configuration.settings import settings

    return settings.calculator


class CalculateTool(Tool):
    """Deterministic local mathematics across all engine operations."""

    metadata = ToolMetadata(
        name="calculate",
        description=(
            "Exact local math: arithmetic, algebra, calculus, matrices, "
            "statistics, units. Returns exact and numeric results."
        ),
        category="calculator",
        permission=PermissionLevel.LOW,
        tags=("calculator", "math", "local"),
        parameters={
            "type": "object",
            "properties": {
                "operation": {"type": "string"},
                "expression": {"type": "string"},
                "equation": {"type": "string"},
                "equations": {"type": "string"},
                "variables": {"type": "string"},
                "variable": {"type": "string"},
                "function": {"type": "string"},
                "arguments": {"type": "string"},
                "value": {"type": "string"},
                "from_unit": {"type": "string"},
                "to_unit": {"type": "string"},
                "data": {"type": "string"},
                "params": {"type": "object"},
            },
            "required": ["operation"],
        },
    )

    def __init__(self, engine=None) -> None:
        self._engine = engine

    def _client(self):
        if self._engine is not None:
            return self._engine
        from asis.calculator.engine import build_engine_from_settings

        return build_engine_from_settings()

    def execute(self, **kwargs: Any) -> ToolResult:
        settings = _calculator_settings()
        if not settings.enabled:
            return ToolResult.failure(
                error="CALCULATION_DISABLED: the calculator is disabled "
                "by configuration.",
                tool_name=self.name,
            )
        operation = kwargs.get("operation", "")
        if not isinstance(operation, str) or not operation.strip():
            return ToolResult.failure(
                error="'operation' must be a non-empty string.",
                tool_name=self.name,
            )
        params: dict[str, Any] = {}
        for key in _STRING_ARGS:
            if key in kwargs and kwargs[key] not in (None, ""):
                value = kwargs[key]
                if not isinstance(value, str):
                    return ToolResult.failure(
                        error=f"'{key}' must be a string.",
                        tool_name=self.name,
                    )
                params[key] = value
        raw_params = kwargs.get("params")
        if raw_params is not None:
            if not isinstance(raw_params, dict):
                return ToolResult.failure(
                    error="'params' must be an object.",
                    tool_name=self.name,
                )
            for key, value in raw_params.items():
                params[str(key)] = value if isinstance(value, str) else str(value)
        # Canonical aliases: engine sub-operations and unit endpoints read
        # naturally in tool calls.
        if "operation_detail" in params:
            params["detail"] = params.pop("operation_detail")
        if "from_unit" in params:
            params["from"] = params.pop("from_unit")
        if "to_unit" in params:
            params["to"] = params.pop("to_unit")
        if "from" in kwargs and kwargs["from"] not in (None, ""):
            params["from"] = str(kwargs["from"])
        if "to" in kwargs and kwargs["to"] not in (None, ""):
            params["to"] = str(kwargs["to"])
        try:
            result = self._client().calculate(operation.strip(), params)
        except Exception as exc:  # engine already maps to CALCULATION_* codes
            code = getattr(exc, "code", None)
            message = getattr(exc, "message", None) or str(exc) or "calculation failed."
            if code:
                tail = message.split(": ", 1)[-1] if ": " in message else message
                return ToolResult.failure(
                    error=f"{code}: {tail}",
                    tool_name=self.name,
                )
            return ToolResult.failure(
                error=f"CALCULATION_PROVIDER_ERROR: {message}",
                tool_name=self.name,
            )
        return ToolResult.ok(
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
            tool_name=self.name,
        )


def build_calculator_tools(engine=None) -> list[Tool]:
    """Build the calculator tools bound to ``engine`` (default if None)."""
    return [CalculateTool(engine)]


def register_calculator_tools(registry, engine=None) -> list[str]:
    """Register calculator tools on ``registry``; returns registered names."""
    names: list[str] = []
    for tool in build_calculator_tools(engine):
        registry.register(tool)
        names.append(tool.name)
    return names
