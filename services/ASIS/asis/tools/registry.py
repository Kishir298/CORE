"""
Tool registry for A.S.I.S.
"""

from __future__ import annotations

from threading import RLock

from asis.errors import ToolNotFoundError, ToolValidationError
from asis.logging.logger import get_logger

from .base import Tool


class ToolRegistry:
    """Thread-safe registry of available A.S.I.S. tools."""

    def __init__(self) -> None:
        self._logger = get_logger("tools.registry")
        self._tools: dict[str, Tool] = {}
        self._lock = RLock()

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        if not isinstance(tool, Tool):
            raise ToolValidationError(f"Not a Tool instance: {type(tool).__name__}.")

        with self._lock:
            if tool.name in self._tools:
                raise ToolValidationError(f"Tool already registered: {tool.name}")

            self._tools[tool.name] = tool

        self._logger.debug("Registered tool: %s", tool.name)

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry."""
        with self._lock:
            self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        """Return a registered tool or None."""
        with self._lock:
            return self._tools.get(name)

    def require(self, name: str) -> Tool:
        """Return a tool or raise an error if unavailable."""
        tool = self.get(name)

        if tool is None:
            raise ToolNotFoundError(f"Tool not registered: {name}")

        return tool

    def list_tools(self) -> list[Tool]:
        """Return all registered tools."""
        with self._lock:
            return list(self._tools.values())

    def list_names(self) -> list[str]:
        """Return all registered tool names."""
        with self._lock:
            return sorted(self._tools)

    def clear(self) -> None:
        """Remove every registered tool."""
        with self._lock:
            self._tools.clear()
