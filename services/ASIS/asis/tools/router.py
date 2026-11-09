"""
Tool routing for A.S.I.S.
"""

from __future__ import annotations

from typing import Any

from asis.logging.logger import get_logger

from .executor import ToolExecutor
from .registry import ToolRegistry
from .result import ToolResult


def build_executor(executor: ToolExecutor | None = None) -> ToolExecutor:
    """Return an executor bound to the configured tools.timeout."""
    if executor is not None:
        return executor
    from asis.configuration import settings

    return ToolExecutor(timeout=settings.tools.timeout)


class ToolRouter:
    """Routes tool requests to registered tools."""

    def __init__(
        self,
        registry: ToolRegistry,
        executor: ToolExecutor | None = None,
    ) -> None:
        self._logger = get_logger("tools.router")
        self.registry = registry
        self.executor = build_executor(executor)

    def execute(
        self,
        tool_name: str,
        **kwargs: Any,
    ) -> ToolResult:
        """Route a tool request."""
        tool = self.registry.get(tool_name)

        if tool is None:
            self._logger.warning("Unknown tool requested: %s", tool_name)

            return ToolResult.failure(
                error=f"Tool not found: {tool_name}",
                tool_name=tool_name,
            )

        return self.executor.execute(tool, **kwargs)
