"""
Echo tool for A.S.I.S.
"""

from __future__ import annotations

from ..base import Tool, ToolMetadata
from ..result import ToolResult


class EchoTool(Tool):
    """Return whatever text is passed to it (test/demo helper)."""

    metadata = ToolMetadata(
        name="echo",
        description="Repeat the given text back.",
        category="utility",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    )

    def execute(self, **kwargs):
        text = kwargs.get("text", "")

        if not isinstance(text, str) or not text.strip():
            return ToolResult.failure(
                error="'text' must be a non-empty string.",
                tool_name=self.name,
            )

        return ToolResult.ok(
            data={"text": text},
            tool_name=self.name,
        )
