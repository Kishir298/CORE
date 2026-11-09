"""
Standard tool execution results.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    """Result returned by an A.S.I.S. tool."""

    success: bool
    data: Any = None
    error: str | None = None
    tool_name: str | None = None

    @classmethod
    def ok(
        cls,
        data: Any = None,
        tool_name: str | None = None,
    ) -> ToolResult:
        """Create a successful result."""
        return cls(
            success=True,
            data=data,
            tool_name=tool_name,
        )

    @classmethod
    def failure(
        cls,
        error: str,
        tool_name: str | None = None,
    ) -> ToolResult:
        """Create a failed result."""
        return cls(
            success=False,
            error=error,
            tool_name=tool_name,
        )
