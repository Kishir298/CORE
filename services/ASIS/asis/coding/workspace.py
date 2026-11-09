"""
Coding workspace abstraction for A.S.C.S.

The workspace is explicit, bounded and validated. All file operations
resolve through the existing ``resolve_sandbox_path`` helper so paths
can never escape the workspace (``../``, absolute outsiders, symlink
escapes).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from asis.errors import ConfigurationError
from asis.permissions.sandbox import SandboxViolation, resolve_sandbox_path


@dataclass(frozen=True)
class CodingWorkspace:
    """Validated root directory for coding operations."""

    root: Path

    def resolve(self, requested: str | Path) -> Path:
        """Resolve a workspace-relative path, rejecting escapes."""
        return resolve_sandbox_path(self.root, Path(requested))

    def relative(self, path: Path) -> str:
        """Return a workspace-relative display string."""
        try:
            return str(path.resolve().relative_to(self.root.resolve()))
        except ValueError:
            return str(path)


def resolve_workspace(explicit: str | Path | None = None) -> CodingWorkspace:
    """Build the active workspace from config or an explicit override."""
    from asis.configuration.settings import settings

    raw = str(explicit) if explicit else settings.coding.workspace
    candidate = Path(raw).expanduser() if raw else Path.cwd()
    try:
        root = candidate.resolve()
    except OSError as exc:
        raise ConfigurationError(f"Invalid coding workspace: {exc}") from exc
    if not root.is_dir():
        raise ConfigurationError(f"Invalid coding workspace: not a directory: {root}")
    return CodingWorkspace(root=root)


__all__ = ["CodingWorkspace", "SandboxViolation", "resolve_workspace"]
