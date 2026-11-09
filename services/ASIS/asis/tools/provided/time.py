"""
Current time tool for A.S.I.S.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..base import Tool, ToolMetadata
from ..result import ToolResult


class CurrentTimeTool(Tool):
    """Return the current UTC time."""

    metadata = ToolMetadata(
        name="current_time",
        description="Return the current UTC date and time.",
        category="utility",
    )

    def execute(self, **kwargs):
        now = datetime.now(UTC)

        return ToolResult.ok(
            data={
                "iso": now.isoformat(),
                "timestamp": now.timestamp(),
            },
            tool_name=self.name,
        )
