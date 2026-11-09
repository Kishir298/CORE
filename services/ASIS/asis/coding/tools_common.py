"""Shared constants and helpers for A.S.I.S. coding tools.

Split out of tools.py with zero behavior change.
"""

from __future__ import annotations

import subprocess
import time

from asis.tools.result import ToolResult

_SKIP_DIRS = frozenset(
    {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        ".ruff_cache",
        ".pytest_cache",
        ".mypy_cache",
        "node_modules",
        "htmlcov",
    }
)
_TEXT_SUFFIXES = frozenset(
    {
        ".py",
        ".md",
        ".txt",
        ".toml",
        ".cfg",
        ".ini",
        ".json",
        ".yaml",
        ".yml",
        ".js",
        ".ts",
        ".tsx",
        ".css",
        ".html",
        ".sh",
        ".env.example",
    }
)
_ALLOW_COMMANDS = frozenset({"pytest", "python", "git"})


def _limits() -> tuple[int, int, int]:
    from asis.configuration.settings import settings

    return (
        settings.coding.max_file_size,
        settings.coding.max_output_size,
        settings.coding.command_timeout,
    )


def _fail(name: str, error: str) -> ToolResult:
    return ToolResult.failure(error=error, tool_name=name)


def _run_argv(
    tool_name: str,
    workspace,
    argv: list[str],
    timeout: int,
) -> ToolResult:
    import sys

    _, max_output, _ = _limits()
    # Resolve the `python` launcher to the running interpreter so the
    # tool works on systems that only provide `python3`.
    resolved = [sys.executable if arg == "python" else arg for arg in argv]
    started = time.monotonic()
    try:
        proc = subprocess.run(
            resolved,
            cwd=workspace.root,
            input="",
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        return _fail(tool_name, f"Command timed out after {timeout}s: {exc}")
    except OSError as exc:
        return _fail(tool_name, f"Command failed to start: {exc}")
    duration = time.monotonic() - started
    stdout = (proc.stdout or "")[-max_output:]
    stderr = (proc.stderr or "")[-max_output:]
    return ToolResult.ok(
        data={
            "command": " ".join(argv),
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "duration": round(duration, 3),
            "success": proc.returncode == 0,
            "truncated": len(proc.stdout or "") > max_output
            or len(proc.stderr or "") > max_output,
        },
        tool_name=tool_name,
    )


