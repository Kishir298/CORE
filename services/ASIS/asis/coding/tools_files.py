"""Workspace file tools: read, write, list, search.

Split out of tools.py with zero behavior change.
"""

from __future__ import annotations

from asis.coding.tools_common import _SKIP_DIRS, _TEXT_SUFFIXES, _fail, _limits
from asis.permissions.models import PermissionLevel
from asis.permissions.sandbox import SandboxViolation
from asis.tools.base import Tool, ToolMetadata
from asis.tools.result import ToolResult

from .workspace import CodingWorkspace


class ReadFileTool(Tool):
    """Read a workspace-relative file (bounded)."""

    metadata = ToolMetadata(
        name="read_file",
        description="Read a workspace-relative file and return its contents.",
        category="coding",
        permission=PermissionLevel.SAFE,
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )

    def __init__(self, workspace: CodingWorkspace) -> None:
        self.workspace = workspace

    def execute(self, **kwargs) -> ToolResult:
        path_arg = kwargs.get("path", "")
        if not isinstance(path_arg, str) or not path_arg.strip():
            return _fail(self.name, "'path' must be a non-empty string.")
        max_file, _, _ = _limits()
        try:
            target = self.workspace.resolve(path_arg)
        except SandboxViolation as exc:
            return _fail(self.name, str(exc))
        if not target.is_file():
            return _fail(self.name, f"File not found: {path_arg}")
        try:
            size = target.stat().st_size
        except OSError as exc:
            return _fail(self.name, f"Cannot stat file: {exc}")
        if size > max_file:
            return _fail(
                self.name,
                f"File too large ({size} bytes, limit {max_file}).",
            )
        try:
            content = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return _fail(self.name, f"Cannot read file: {exc}")
        truncated = False
        if len(content) > max_file:
            content = content[:max_file]
            truncated = True
        return ToolResult.ok(
            data={
                "path": self.workspace.relative(target),
                "content": content,
                "truncated": truncated,
            },
            tool_name=self.name,
        )


class WriteFileTool(Tool):
    """Write exact contents to a workspace-relative file (confirm-gated)."""

    metadata = ToolMetadata(
        name="write_file",
        description="Write exact contents to a workspace-relative file.",
        category="coding",
        permission=PermissionLevel.HIGH,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    )

    def __init__(self, workspace: CodingWorkspace) -> None:
        self.workspace = workspace

    def execute(self, **kwargs) -> ToolResult:
        path_arg = kwargs.get("path", "")
        content = kwargs.get("content")
        if not isinstance(path_arg, str) or not path_arg.strip():
            return _fail(self.name, "'path' must be a non-empty string.")
        if not isinstance(content, str):
            return _fail(self.name, "'content' must be a string.")
        max_file, _, _ = _limits()
        if len(content.encode("utf-8")) > max_file:
            return _fail(
                self.name,
                f"Content too large (limit {max_file} bytes).",
            )
        try:
            target = self.workspace.resolve(path_arg)
        except SandboxViolation as exc:
            return _fail(self.name, str(exc))
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            return _fail(self.name, f"Write failed: {exc}")
        return ToolResult.ok(
            data={"path": self.workspace.relative(target), "bytes": len(content)},
            tool_name=self.name,
        )


class ListDirectoryTool(Tool):
    """List a workspace-relative directory (bounded)."""

    metadata = ToolMetadata(
        name="list_directory",
        description="List entries of a workspace-relative directory.",
        category="coding",
        permission=PermissionLevel.SAFE,
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
        },
    )

    def __init__(self, workspace: CodingWorkspace) -> None:
        self.workspace = workspace

    def execute(self, **kwargs) -> ToolResult:
        path_arg = kwargs.get("path", ".")
        if not isinstance(path_arg, str) or not path_arg.strip():
            return _fail(self.name, "'path' must be a non-empty string.")
        try:
            target = self.workspace.resolve(path_arg)
        except SandboxViolation as exc:
            return _fail(self.name, str(exc))
        if not target.is_dir():
            return _fail(self.name, f"Not a directory: {path_arg}")
        try:
            entries = sorted(
                (p.name + ("/" if p.is_dir() else ""))
                for p in target.iterdir()
                if p.name not in _SKIP_DIRS
            )
        except OSError as exc:
            return _fail(self.name, f"Listing failed: {exc}")
        truncated = False
        if len(entries) > 200:
            entries = entries[:200]
            truncated = True
        return ToolResult.ok(
            data={
                "path": self.workspace.relative(target),
                "entries": entries,
                "truncated": truncated,
            },
            tool_name=self.name,
        )


class SearchFilesTool(Tool):
    """Search workspace text files for a substring (bounded)."""

    metadata = ToolMetadata(
        name="search_files",
        description="Search workspace files for a text pattern.",
        category="coding",
        permission=PermissionLevel.LOW,
        parameters={
            "type": "object",
            "properties": {"pattern": {"type": "string"}},
            "required": ["pattern"],
        },
    )

    def __init__(self, workspace: CodingWorkspace) -> None:
        self.workspace = workspace

    def execute(self, **kwargs) -> ToolResult:
        pattern = kwargs.get("pattern", "")
        if not isinstance(pattern, str) or not pattern.strip():
            return _fail(self.name, "'pattern' must be a non-empty string.")
        needle = pattern.strip()
        _, max_output, _ = _limits()
        matches: list[dict] = []
        scanned = 0
        for path in sorted(self.workspace.root.rglob("*")):
            if len(matches) >= 50:
                break
            if not path.is_file() or any(part in _SKIP_DIRS for part in path.parts):
                continue
            if path.suffix not in _TEXT_SUFFIXES and path.name != ".env.example":
                continue
            try:
                if path.stat().st_size > 200_000:
                    continue
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            scanned += 1
            if scanned > 2000:
                break
            for lineno, line in enumerate(text.splitlines(), 1):
                if needle in line:
                    matches.append(
                        {
                            "path": str(
                                path.resolve().relative_to(
                                    self.workspace.root.resolve()
                                )
                            ),
                            "line": lineno,
                            "text": line.strip()[:200],
                        }
                    )
                    if len(matches) >= 50:
                        break
        truncated = len(matches) >= 50
        _ = max_output
        return ToolResult.ok(
            data={"pattern": needle, "matches": matches, "truncated": truncated},
            tool_name=self.name,
        )


