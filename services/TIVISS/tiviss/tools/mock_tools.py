"""Safe, deterministic mock tools for development and testing.

These tools perform no I/O and grant no system access; they exist to exercise
the tool framework end to end.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..permissions.permissions import Permission
from .interface import Tool, ToolError, ToolResult, ToolStatus


class EchoTool(Tool):
    """Echoes back its input."""

    @property
    def tool_id(self) -> str:
        return "echo"

    @property
    def name(self) -> str:
        return "Echo"

    @property
    def description(self) -> str:
        return "Echo back the provided text."

    @property
    def permission(self) -> Permission:
        return Permission.of("tools.echo")

    def validate_input(self, params: Mapping[str, Any]) -> Mapping[str, Any]:
        if "text" not in params:
            raise ToolError("echo requires a 'text' parameter")
        return {"text": str(params["text"])}

    def execute(self, params: Mapping[str, Any]) -> ToolResult:
        return ToolResult(
            tool_id=self.tool_id, status=ToolStatus.OK, output=params["text"]
        )


class SumTool(Tool):
    """Adds a list of integers."""

    @property
    def tool_id(self) -> str:
        return "sum"

    @property
    def name(self) -> str:
        return "Sum"

    @property
    def description(self) -> str:
        return "Sum a list of integers passed as 'values'."

    @property
    def permission(self) -> Permission:
        return Permission.of("tools.math")

    def validate_input(self, params: Mapping[str, Any]) -> Mapping[str, Any]:
        raw = params.get("values")
        if not isinstance(raw, (list, tuple)):
            raise ToolError("sum requires a 'values' list of integers")
        try:
            values = tuple(int(v) for v in raw)
        except (TypeError, ValueError) as exc:
            raise ToolError(f"sum values must be integers: {exc}") from exc
        return {"values": values}

    def execute(self, params: Mapping[str, Any]) -> ToolResult:
        total = sum(params["values"])
        return ToolResult(
            tool_id=self.tool_id,
            status=ToolStatus.OK,
            output=total,
            metadata={"terms": params["values"], "count": len(params["values"])},
        )


class FailingTool(Tool):
    """A tool that always fails, for failure-path testing."""

    def __init__(self, failure_message: str = "boom") -> None:
        self._failure_message = failure_message

    @property
    def tool_id(self) -> str:
        return "failing"

    @property
    def name(self) -> str:
        return "Failing"

    @property
    def description(self) -> str:
        return "Always fails with a ToolError."

    @property
    def permission(self) -> Permission:
        return Permission.of("tools.safe")

    def execute(self, params: Mapping[str, Any]) -> ToolResult:
        raise ToolError(self._failure_message)
