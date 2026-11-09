"""
Git update installer for ASIS repository.
"""

from __future__ import annotations

from pathlib import Path

from . import BaseInstaller, InstallResult


class GitInstaller(BaseInstaller):
    """Installs git repository updates."""

    @property
    def component_name(self) -> str:
        return "git"

    def install(self, update_info: dict) -> InstallResult:
        """Pull latest changes from upstream."""
        repo_root = self._find_repo_root()
        if not repo_root:
            return InstallResult(
                component="git",
                success=False,
                message="Not a git repository or repo root not found",
            )

        try:
            # Stash any local changes first
            returncode, stdout, stderr = self._run_command(
                ["git", "stash", "--include-untracked"], cwd=repo_root
            )
            stashed = returncode == 0

            # Pull with rebase
            returncode, stdout, stderr = self._run_command(
                ["git", "pull", "--rebase"], cwd=repo_root
            )

            if returncode != 0:
                # Try to restore stash on failure
                if stashed:
                    self._run_command(["git", "stash", "pop"], cwd=repo_root)
                return InstallResult(
                    component="git",
                    success=False,
                    message=f"Git pull failed: {stderr}",
                    details={"stdout": stdout, "stderr": stderr},
                )

            # Restore stash if there were changes
            if stashed:
                returncode, stdout, stderr = self._run_command(
                    ["git", "stash", "pop"], cwd=repo_root
                )
                if returncode != 0:
                    return InstallResult(
                        component="git",
                        success=True,
                        message="Git pull succeeded but stash restore failed - check 'git stash list'",
                        requires_restart=True,
                        details={"stash_restore_failed": True},
                    )

            # Get new commit hash
            returncode, new_hash, _ = self._run_command(
                ["git", "rev-parse", "--short", "HEAD"], cwd=repo_root
            )

            return InstallResult(
                component="git",
                success=True,
                message=f"Updated to {new_hash[:8] if new_hash else 'latest'}",
                requires_restart=True,
                details={"new_commit": new_hash[:8] if new_hash else "unknown"},
            )

        except Exception as e:
            return InstallResult(
                component="git",
                success=False,
                message=f"Git install failed: {e}",
            )

    def _find_repo_root(self) -> str | None:
        """Find the git repository root containing ASIS."""
        current = Path(__file__).resolve()
        for parent in [current] + list(current.parents):
            if (parent / ".git").exists():
                if (parent / "asis").exists() or parent.name == "ASIS":
                    return str(parent)
        return None
