"""
Pip update checker for ASIS Python dependencies.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import BaseChecker, ComponentUpdate


class PipChecker(BaseChecker):
    """Checks for outdated Python packages."""

    @property
    def component_name(self) -> str:
        return "pip"

    def check(self) -> ComponentUpdate:
        """Check for outdated pip packages."""
        try:
            # Find requirements files
            req_files = self._find_requirements_files()
            if not req_files:
                return ComponentUpdate(
                    component="pip",
                    current_version="unknown",
                    available_version="",
                    description="No requirements files found",
                )

            # Run pip list --outdated --format=json
            returncode, stdout, stderr = self._run_command(
                [sys.executable, "-m", "pip", "list", "--outdated", "--format=json"]
            )
            if returncode != 0:
                return ComponentUpdate(
                    component="pip",
                    current_version="error",
                    available_version="",
                    description=f"pip list failed: {stderr}",
                )

            try:
                outdated = json.loads(stdout) if stdout.strip() else []
            except json.JSONDecodeError:
                return ComponentUpdate(
                    component="pip",
                    current_version="error",
                    available_version="",
                    description="Failed to parse pip output",
                )

            if not outdated:
                return ComponentUpdate(
                    component="pip",
                    current_version="up-to-date",
                    available_version="",
                    description="All packages up to date",
                )

            # Filter to only packages in our requirements
            relevant = self._filter_relevant_packages(outdated, req_files)

            if not relevant:
                return ComponentUpdate(
                    component="pip",
                    current_version="up-to-date",
                    available_version="",
                    description="No relevant packages outdated",
                )

            # Build summary
            pkg_list = ", ".join(f"{p['name']} ({p['version']} -> {p['latest_version']})" for p in relevant[:5])
            more = f" +{len(relevant) - 5} more" if len(relevant) > 5 else ""

            return ComponentUpdate(
                component="pip",
                current_version=f"{len(relevant)} outdated",
                available_version="latest",
                description=f"{len(relevant)} package(s) outdated: {pkg_list}{more}",
                install_command="pip install --upgrade -r requirements/ai.txt -r requirements/voice.txt -r requirements/tui.txt",
                metadata={"packages": relevant},
            )

        except Exception as e:
            return ComponentUpdate(
                component="pip",
                current_version="error",
                available_version="",
                description=f"Pip check failed: {e}",
            )

    def _find_requirements_files(self) -> list[Path]:
        """Find ASIS requirements files."""
        repo_root = self._find_repo_root()
        if not repo_root:
            return []

        req_dir = Path(repo_root) / "requirements"
        if not req_dir.exists():
            return []

        files = list(req_dir.glob("*.txt"))
        # Always include base.txt if it exists
        base = req_dir / "base.txt"
        if base.exists() and base not in files:
            files.insert(0, base)
        return files

    def _filter_relevant_packages(
        self, outdated: list[dict], req_files: list[Path]
    ) -> list[dict]:
        """Filter outdated packages to only those in our requirements."""
        # Parse all requirements
        required_packages = set()
        for req_file in req_files:
            try:
                content = req_file.read_text()
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("-"):
                        # Extract package name (before version specifier)
                        pkg = line.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].split("[")[0].strip()
                        if pkg:
                            required_packages.add(pkg.lower())
            except Exception:
                pass

        # Filter outdated to only required packages
        relevant = []
        for pkg in outdated:
            if pkg.get("name", "").lower() in required_packages:
                relevant.append(pkg)

        return relevant

    def _find_repo_root(self) -> str | None:
        """Find the git repository root containing ASIS."""
        current = Path(__file__).resolve()
        for parent in [current] + list(current.parents):
            if (parent / ".git").exists():
                if (parent / "asis").exists() or parent.name == "ASIS":
                    return str(parent)
        return None
