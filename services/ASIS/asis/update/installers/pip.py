"""
Pip update installer for ASIS Python dependencies.
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import BaseInstaller, InstallResult


class PipInstaller(BaseInstaller):
    """Installs pip package updates."""

    @property
    def component_name(self) -> str:
        return "pip"

    def install(self, update_info: dict) -> InstallResult:
        """Upgrade pip packages from requirements files."""
        repo_root = self._find_repo_root()
        if not repo_root:
            return InstallResult(
                component="pip",
                success=False,
                message="ASIS repo root not found",
            )

        req_dir = Path(repo_root) / "requirements"
        if not req_dir.exists():
            return InstallResult(
                component="pip",
                success=False,
                message="Requirements directory not found",
            )

        # Find all requirements files
        req_files = list(req_dir.glob("*.txt"))
        if not req_files:
            return InstallResult(
                component="pip",
                success=False,
                message="No requirements files found",
            )

        try:
            # Upgrade each requirements file
            results = []
            for req_file in req_files:
                returncode, stdout, stderr = self._run_command(
                    [sys.executable, "-m", "pip", "install", "--upgrade", "-r", str(req_file)]
                )
                results.append({
                    "file": req_file.name,
                    "success": returncode == 0,
                    "stdout": stdout,
                    "stderr": stderr,
                })

            failed = [r for r in results if not r["success"]]
            if failed:
                return InstallResult(
                    component="pip",
                    success=False,
                    message=f"Failed to upgrade {len(failed)} requirements file(s)",
                    details={"results": results},
                )

            return InstallResult(
                component="pip",
                success=True,
                message=f"Upgraded {len(results)} requirements file(s)",
                requires_restart=True,
                details={"results": results},
            )

        except Exception as e:
            return InstallResult(
                component="pip",
                success=False,
                message=f"Pip install failed: {e}",
            )

    def _find_repo_root(self) -> str | None:
        """Find the git repository root containing ASIS."""
        current = Path(__file__).resolve()
        for parent in [current] + list(current.parents):
            if (parent / ".git").exists():
                if (parent / "asis").exists() or parent.name == "ASIS":
                    return str(parent)
        return None
