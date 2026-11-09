"""
Update installers for ASIS components.

Each installer applies updates for a specific component.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class InstallResult:
    """Result of an installation attempt."""

    component: str
    success: bool
    message: str
    requires_restart: bool = False
    details: dict = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


class BaseInstaller(ABC):
    """Abstract base class for update installers."""

    @property
    @abstractmethod
    def component_name(self) -> str:
        """Unique identifier for this component."""
        pass

    @abstractmethod
    def install(self, update_info: dict) -> InstallResult:
        """
        Install the update.

        Args:
            update_info: Information from the corresponding checker's ComponentUpdate.

        Returns:
            InstallResult indicating success/failure and any restart requirement.
        """
        pass

    def _run_command(self, cmd: list[str], cwd: str | None = None) -> tuple[int, str, str]:
        """Run a command and return (returncode, stdout, stderr)."""
        import subprocess
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes for installs
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)
