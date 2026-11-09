"""Workspace command tools: tests + allowlisted commands.

Split out of tools.py with zero behavior change.
"""

from __future__ import annotations

from asis.coding.tools_common import _ALLOW_COMMANDS, _fail, _run_argv
from asis.permissions.models import PermissionLevel
from asis.tools.base import Tool, ToolMetadata
from asis.tools.result import ToolResult

from .workspace import CodingWorkspace


class RunTestsTool(Tool):
    """Run the project test suite (allowlisted pytest, confirm-gated)."""

    metadata = ToolMetadata(
        name="run_tests",
        description="Run the project pytest suite and return structured results.",
        category="coding",
        permission=PermissionLevel.HIGH,
        parameters={
            "type": "object",
            "properties": {"args": {"type": "array"}},
        },
    )

    def __init__(self, workspace: CodingWorkspace) -> None:
        self.workspace = workspace

    def execute(self, **kwargs) -> ToolResult:
        from asis.configuration.settings import settings

        extra = kwargs.get("args", [])
        if extra is None:
            extra = []
        if not isinstance(extra, list) or not all(isinstance(a, str) for a in extra):
            return _fail(self.name, "'args' must be a list of strings.")
        if any(a.startswith("-") and a not in ("-q", "-x", "-k") for a in extra):
            return _fail(self.name, "Only -q/-x/-k flags are allowed.")
        argv = ["python", "-m", "pytest", "-q", *extra]
        return _run_argv(
            self.name, self.workspace, argv, settings.coding.command_timeout
        )


class RunCommandTool(Tool):
    """Run an allowlisted command (pytest/python/git only, no shell)."""

    metadata = ToolMetadata(
        name="run_command",
        description="Run an allowlisted project command (no shell).",
        category="coding",
        permission=PermissionLevel.HIGH,
        parameters={
            "type": "object",
            "properties": {"argv": {"type": "array"}},
            "required": ["argv"],
        },
    )

    def __init__(self, workspace: CodingWorkspace) -> None:
        self.workspace = workspace

    def execute(self, **kwargs) -> ToolResult:
        from asis.configuration.settings import settings

        argv = kwargs.get("argv")
        if (
            not isinstance(argv, list)
            or not argv
            or not all(isinstance(a, str) for a in argv)
        ):
            return _fail(self.name, "'argv' must be a non-empty list of strings.")
        if argv[0] not in _ALLOW_COMMANDS:
            return _fail(
                self.name,
                f"Command not allowed: {argv[0]!r} (allowed: pytest, python, git).",
            )
        return _run_argv(
            self.name, self.workspace, argv, settings.coding.command_timeout
        )


