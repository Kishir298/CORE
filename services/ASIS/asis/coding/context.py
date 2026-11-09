"""
Repository-aware context for A.S.C.S. coding mode.

Selective by design: workspace path, shallow project structure, git
status and recent diff signal — never a full repository dump. Personal
memory stays separate; repository facts from tools are authoritative.
"""

from __future__ import annotations

import subprocess

from asis.logging.logger import get_logger

from .workspace import CodingWorkspace

_SKIP_DIRS = frozenset(
    {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        ".ruff_cache",
        ".pytest_cache",
        "node_modules",
        ".mypy_cache",
        "htmlcov",
        ".coverage",
    }
)


class CodingContextResolver:
    """Build a bounded repository context block for the model."""

    def __init__(
        self,
        workspace: CodingWorkspace,
        max_entries: int = 40,
        max_chars: int = 4000,
    ) -> None:
        self.workspace = workspace
        self.max_entries = max(1, max_entries)
        self.max_chars = max(256, max_chars)
        self.logger = get_logger("coding.context")

    def _structure(self) -> list[str]:
        entries: list[str] = []
        try:
            for path in sorted(self.workspace.root.iterdir()):
                if len(entries) >= self.max_entries:
                    break
                name = path.name
                if (
                    path.is_dir()
                    and name in _SKIP_DIRS
                    or name in (".git", ".venv", ".ruff_cache", ".pytest_cache")
                ):
                    continue
                entries.append(f"{name}/" if path.is_dir() else name)
        except OSError as exc:
            self.logger.warning("Workspace listing failed: %s", exc)
        return entries

    def _git_status(self) -> str:
        try:
            proc = subprocess.run(
                ["git", "status", "--short"],
                cwd=self.workspace.root,
                capture_output=True,
                text=True,
                timeout=10,
                shell=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self.logger.warning("git status failed: %s", exc)
            return ""
        if proc.returncode != 0:
            return ""
        return proc.stdout.strip()[:1000]

    def build(self, query: str = "") -> str:
        """Return the REPOSITORY CONTEXT block ("" when workspace unreadable)."""
        _ = query
        lines = [f"REPOSITORY CONTEXT:\n- Workspace: {self.workspace.root}"]
        structure = self._structure()
        if structure:
            lines.append("- Top-level: " + ", ".join(structure))
        status = self._git_status()
        if status:
            lines.append("- Git status:\n" + status)
        lines.append(
            "- Repository facts above are authoritative over remembered assumptions."
        )
        text = "\n".join(lines)
        if len(text) > self.max_chars:
            text = text[: self.max_chars] + "\n- (truncated)"
        return text
