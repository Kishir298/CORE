"""Coding tools for A.S.C.S. (workspace-bound, permission-gated).

All tools run through the shared ``ToolRegistry → ToolRouter →
ToolExecutor`` path with the existing permission levels: reads are
SAFE/LOW (auto-approved), writes and command execution require
confirmation (HIGH/CRITICAL). Command execution uses allowlisted argv
with ``shell=False``, a workspace CWD, and enforced timeouts — never
unrestricted shell access.

Thin facade: implementations live in tools_files/tools_run/tools_git.
This module is the permanent public surface — import tool classes and
``build_coding_registry`` from here, not from the split modules.
"""

from __future__ import annotations

from asis.tools.registry import ToolRegistry

from .tools_files import (
    ListDirectoryTool,
    ReadFileTool,
    SearchFilesTool,
    WriteFileTool,
)
from .tools_git import GitAddTool, GitCommitTool, GitDiffTool, GitStatusTool
from .tools_run import RunCommandTool, RunTestsTool
from .workspace import CodingWorkspace


def build_coding_registry(workspace: CodingWorkspace) -> ToolRegistry:
    """Build the coding tool registry bound to a workspace."""
    registry = ToolRegistry()
    for tool in (
        ReadFileTool(workspace),
        SearchFilesTool(workspace),
        ListDirectoryTool(workspace),
        WriteFileTool(workspace),
        RunTestsTool(workspace),
        RunCommandTool(workspace),
        GitStatusTool(workspace),
        GitDiffTool(workspace),
        GitAddTool(workspace),
        GitCommitTool(workspace),
    ):
        registry.register(tool)
    return registry


__all__ = [
    "GitAddTool",
    "GitCommitTool",
    "GitDiffTool",
    "GitStatusTool",
    "ListDirectoryTool",
    "ReadFileTool",
    "RunCommandTool",
    "RunTestsTool",
    "SearchFilesTool",
    "WriteFileTool",
    "build_coding_registry",
]
