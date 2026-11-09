"""
Filesystem sandbox helpers for A.S.I.S.

Tools that touch the filesystem must confine writes to an allowed
directory so no path can escape the sandbox.
"""

from __future__ import annotations

from pathlib import Path

from asis.errors import PermissionError


class SandboxViolation(PermissionError):
    """Raised when an operation escapes its permitted directory."""


def resolve_sandbox_path(
    base_directory: Path,
    requested_path: Path,
) -> Path:
    """Resolve a path and ensure it remains inside the sandbox."""
    base = base_directory.expanduser().resolve()
    target = requested_path.expanduser()

    if not target.is_absolute():
        target = base / target

    target = target.resolve()

    try:
        target.relative_to(base)
    except ValueError as exc:
        raise SandboxViolation(f"Path escapes sandbox: {target}") from exc

    return target
