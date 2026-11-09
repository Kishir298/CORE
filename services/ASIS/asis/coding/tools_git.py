"""Workspace git tools: status, diff, add, commit.

Split out of tools.py with zero behavior change.
"""

from __future__ import annotations

from asis.coding.tools_common import _fail, _limits, _run_argv
from asis.permissions.models import PermissionLevel
from asis.tools.base import Tool, ToolMetadata
from asis.tools.result import ToolResult

from .workspace import CodingWorkspace, SandboxViolation


class GitStatusTool(Tool):
    """Return structured git status (read-only)."""

    metadata = ToolMetadata(
        name="git_status",
        description="Return the workspace git status (read-only).",
        category="coding",
        permission=PermissionLevel.SAFE,
    )

    def __init__(self, workspace: CodingWorkspace) -> None:
        self.workspace = workspace

    def execute(self, **kwargs) -> ToolResult:
        from asis.configuration.settings import settings

        result = _run_argv(
            self.name,
            self.workspace,
            ["git", "status", "--short", "--branch"],
            settings.coding.command_timeout,
        )
        if not result.success:
            return result
        return ToolResult.ok(
            data={
                "status": result.data["stdout"],
                "clean": not result.data["stdout"].strip(),
            },
            tool_name=self.name,
        )


class GitDiffTool(Tool):
    """Return the workspace git diff (read-only, bounded)."""

    metadata = ToolMetadata(
        name="git_diff",
        description="Return the workspace git diff (read-only).",
        category="coding",
        permission=PermissionLevel.SAFE,
        parameters={
            "type": "object",
            "properties": {"args": {"type": "array"}},
        },
    )

    def __init__(self, workspace: CodingWorkspace) -> None:
        self.workspace = workspace

    def execute(self, **kwargs) -> ToolResult:
        from asis.configuration.settings import settings

        _, max_output, _ = _limits()
        args = kwargs.get("args", [])
        if args is None:
            args = []
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            return _fail(self.name, "'args' must be a list of strings.")
        if any(a.startswith("-") and a not in ("--stat", "--cached") for a in args):
            return _fail(self.name, "Only --stat/--cached flags are allowed.")
        result = _run_argv(
            self.name,
            self.workspace,
            ["git", "diff", *args],
            settings.coding.command_timeout,
        )
        if not result.success:
            return result
        diff = result.data["stdout"]
        return ToolResult.ok(
            data={
                "diff": diff[:max_output],
                "truncated": len(diff) > max_output,
            },
            tool_name=self.name,
        )


class GitAddTool(Tool):
    """Stage workspace files (requires confirmation, never auto-commit)."""

    metadata = ToolMetadata(
        name="git_add",
        description="Stage workspace files with git add (confirm-gated).",
        category="coding",
        permission=PermissionLevel.HIGH,
        parameters={
            "type": "object",
            "properties": {"paths": {"type": "array"}},
            "required": ["paths"],
        },
    )

    def __init__(self, workspace: CodingWorkspace) -> None:
        self.workspace = workspace

    def execute(self, **kwargs) -> ToolResult:
        from asis.configuration.settings import settings

        paths = kwargs.get("paths", [])
        if (
            not isinstance(paths, list)
            or not paths
            or not all(isinstance(p, str) for p in paths)
        ):
            return _fail(self.name, "'paths' must be a non-empty list of strings.")
        resolved: list[str] = []
        for item in paths:
            try:
                target = self.workspace.resolve(item)
            except SandboxViolation as exc:
                return _fail(self.name, str(exc))
            resolved.append(
                str(target.resolve().relative_to(self.workspace.root.resolve()))
            )
        return _run_argv(
            self.name,
            self.workspace,
            ["git", "add", "--", *resolved],
            settings.coding.command_timeout,
        )


class GitCommitTool(Tool):
    """Create a commit (requires confirmation; never pushes)."""

    metadata = ToolMetadata(
        name="git_commit",
        description="Create a git commit (confirm-gated, never pushes).",
        category="coding",
        permission=PermissionLevel.CRITICAL,
        parameters={
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    )

    def __init__(self, workspace: CodingWorkspace) -> None:
        self.workspace = workspace

    def execute(self, **kwargs) -> ToolResult:
        from asis.configuration.settings import settings

        message = kwargs.get("message", "")
        if not isinstance(message, str) or not message.strip():
            return _fail(self.name, "'message' must be a non-empty string.")
        if len(message) > 500:
            return _fail(self.name, "Commit message too long (max 500 chars).")
        return _run_argv(
            self.name,
            self.workspace,
            ["git", "commit", "-m", message.strip()],
            settings.coding.command_timeout,
        )


