"""
Git update checker for ASIS repository.
"""

from __future__ import annotations

from pathlib import Path

from . import BaseChecker, ComponentUpdate


class GitChecker(BaseChecker):
    """Checks for git repository updates."""

    @property
    def component_name(self) -> str:
        return "git"

    def check(self) -> ComponentUpdate:
        """Check if git repository has upstream updates."""
        # Find the ASIS repo root
        repo_root = self._find_repo_root()
        if not repo_root:
            return ComponentUpdate(
                component="git",
                current_version="unknown",
                available_version="",
                description="Not a git repository or repo root not found",
            )

        try:
            # Fetch latest from remote (dry-run to avoid modifying state)
            returncode, stdout, stderr = self._run_command(
                ["git", "fetch", "--dry-run"], cwd=repo_root
            )
            if returncode != 0:
                # Fallback: try regular fetch then check status
                returncode, stdout, stderr = self._run_command(
                    ["git", "fetch"], cwd=repo_root
                )
                if returncode != 0:
                    return ComponentUpdate(
                        component="git",
                        current_version=self._get_current_commit(repo_root),
                        available_version="",
                        description=f"Git fetch failed: {stderr}",
                    )

            # Check if we're behind upstream
            returncode, stdout, stderr = self._run_command(
                ["git", "rev-list", "--count", "HEAD..@{u}"], cwd=repo_root
            )
            if returncode != 0:
                # No upstream configured or other issue
                return ComponentUpdate(
                    component="git",
                    current_version=self._get_current_commit(repo_root),
                    available_version="",
                    description="No upstream branch configured or error checking",
                )

            behind_count = int(stdout.strip()) if stdout.strip().isdigit() else 0

            if behind_count > 0:
                # Get the latest commit hash from upstream
                returncode, upstream_hash, _ = self._run_command(
                    ["git", "rev-parse", "@{u}"], cwd=repo_root
                )
                available = upstream_hash[:8] if returncode == 0 else "newer"
                return ComponentUpdate(
                    component="git",
                    current_version=self._get_current_commit(repo_root),
                    available_version=available,
                    description=f"{behind_count} commit(s) behind upstream",
                    install_command="git pull --rebase",
                )

            return ComponentUpdate(
                component="git",
                current_version=self._get_current_commit(repo_root),
                available_version="",
                description="Up to date",
            )

        except Exception as e:
            return ComponentUpdate(
                component="git",
                current_version="error",
                available_version="",
                description=f"Git check failed: {e}",
            )

    def _find_repo_root(self) -> str | None:
        """Find the git repository root containing ASIS."""
        # Start from this file's directory and walk up
        current = Path(__file__).resolve()
        for parent in [current] + list(current.parents):
            if (parent / ".git").exists():
                # Verify it's the ASIS repo by checking for asis/ directory
                if (parent / "asis").exists() or parent.name == "ASIS":
                    return str(parent)
        return None

    def _get_current_commit(self, repo_root: str) -> str:
        """Get current commit hash (short)."""
        returncode, stdout, _ = self._run_command(
            ["git", "rev-parse", "--short", "HEAD"], cwd=repo_root
        )
        return stdout[:8] if returncode == 0 and stdout else "unknown"
