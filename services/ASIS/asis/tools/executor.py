"""
Tool execution engine for A.S.I.S.
"""

from __future__ import annotations

from typing import Any

from asis.events.bus import EventBus
from asis.events.events import Event, EventType
from asis.logging.logger import get_logger

from .authorizer import Authorizer, build_authorizer
from .base import Tool
from .result import ToolResult


class ToolExecutor:
    """Executes registered A.S.I.S. tools safely."""

    def __init__(
        self,
        authorizer: Authorizer | None = None,
        event_bus: EventBus | None = None,
        timeout: float | None = None,
    ) -> None:
        self._logger = get_logger("tools.executor")
        self.authorizer = authorizer or build_authorizer()
        self.event_bus = event_bus
        # Maximum seconds per tool run (None/<=0 disables the bound).
        # Defaults to the configured tools.timeout via build_executor().
        self.timeout = timeout

    def _run_bounded(self, tool: Tool, kwargs: dict[str, Any]) -> Any:
        """Run a tool, enforcing the configured timeout when set."""
        limit = self.timeout
        if limit is None or limit <= 0:
            return tool.execute(**kwargs)
        import threading

        outcome: dict[str, Any] = {}

        def _target() -> None:
            try:
                outcome["result"] = tool.execute(**kwargs)
            except Exception as exc:  # captured, re-raised by caller path
                outcome["error"] = exc

        worker = threading.Thread(target=_target, daemon=True)
        worker.start()
        worker.join(timeout=limit)
        if worker.is_alive():
            return ToolResult.failure(
                error=f"Tool timed out after {limit:g} seconds.",
                tool_name=tool.name,
            )
        if "error" in outcome:
            raise outcome["error"]
        return outcome.get("result")

    def _publish(
        self,
        event_type: EventType,
        tool_name: str,
        **data,
    ) -> None:
        if self.event_bus is None:
            return

        self.event_bus.publish(
            Event(
                type=event_type,
                data={"tool": tool_name, **data},
                source="tools",
            )
        )

    def execute(
        self,
        tool: Tool,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute a tool after authorization."""
        if not self.authorizer(tool):
            self._logger.warning("Tool execution denied: %s", tool.name)
            self._publish(
                EventType.TOOL_DENIED,
                tool_name=tool.name,
            )

            return ToolResult.failure(
                error="Tool execution denied.",
                tool_name=tool.name,
            )

        self._logger.info("Executing tool: %s", tool.name)
        self._publish(EventType.TOOL_EXECUTION_STARTED, tool_name=tool.name)

        try:
            result = self._run_bounded(tool, kwargs)

            if not isinstance(result, ToolResult):
                result = ToolResult.ok(
                    data=result,
                    tool_name=tool.name,
                )

            if result.success:
                self._publish(EventType.TOOL_EXECUTION_FINISHED, tool_name=tool.name)
            else:
                self._logger.warning(
                    "Tool reported failure: %s -> %s",
                    tool.name,
                    result.error,
                )

            return result

        except Exception as exc:
            self._logger.exception("Tool execution failed: %s", tool.name)
            self._publish(
                EventType.TOOL_EXECUTION_FAILED,
                tool_name=tool.name,
                error=str(exc),
            )

            return ToolResult.failure(
                error=str(exc),
                tool_name=tool.name,
            )
