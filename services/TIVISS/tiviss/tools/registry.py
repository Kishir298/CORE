"""Permission-gated tool registry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..permissions.permissions import (
    PermissionContext,
    PermissionDeniedError,
)
from ..permissions.policy import PermissionPolicy
from .interface import Tool, ToolError, ToolResult, ToolStatus


class UnknownToolError(ToolError):
    """Raised when a tool ID is not registered."""

    def __init__(self, tool_id: str) -> None:
        self.tool_id = tool_id
        super().__init__(f"unknown tool: {tool_id}")


class ToolRegistry:
    """Registry that gates every execution through the permission policy.

    Execution flow: tool exists -> permission checks -> input validation ->
    execution -> structured result. Permission failures produce a DENIED
    result instead of raising.
    """

    def __init__(self, *, policy: PermissionPolicy | None = None) -> None:
        from ..permissions.policy import DefaultDenyPolicy

        self.policy = policy or DefaultDenyPolicy()
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.tool_id in self._tools:
            raise ToolError(f"tool already registered: {tool.tool_id}")
        self._tools[tool.tool_id] = tool

    def unregister(self, tool_id: str) -> bool:
        try:
            del self._tools[tool_id]
        except KeyError:
            return False
        return True

    def get(self, tool_id: str) -> Tool | None:
        return self._tools.get(tool_id)

    def list(self) -> tuple[Tool, ...]:
        return tuple(sorted(self._tools.values(), key=lambda t: t.tool_id))

    def __contains__(self, tool_id: str) -> bool:
        return tool_id in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def execute(
        self,
        tool_id: str,
        ctx: PermissionContext,
        params: Mapping[str, Any] | None = None,
    ) -> ToolResult:
        tool = self.get(tool_id)
        if tool is None:
            raise UnknownToolError(tool_id)

        for permission in tool.required_permissions():
            if not self.policy.check(ctx, permission):
                return ToolResult(
                    tool_id=tool_id,
                    status=ToolStatus.DENIED,
                    error=f"permission denied: {permission}",
                    metadata={"permission": permission.name, "source": ctx.source},
                )

        try:
            cleaned = tool.validate_input(dict(params or {}))
            return tool.execute(cleaned)
        except (ToolError, PermissionDeniedError) as exc:
            return ToolResult(tool_id=tool_id, status=ToolStatus.FAILED, error=str(exc))
