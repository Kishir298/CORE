"""
Update checkers for ASIS components.

Each checker implements a standard interface for checking updates
for a specific component (git, pip, ollama models).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ComponentUpdate:
    """Represents an available update for a component."""

    component: str  # e.g., "git", "pip", "ollama_models"
    current_version: str
    available_version: str
    description: str = ""
    install_command: str = ""
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    @property
    def has_update(self) -> bool:
        """True if an update is available."""
        return self.available_version != "" and self.available_version != self.current_version


class BaseChecker(ABC):
    """Abstract base class for update checkers."""

    @property
    @abstractmethod
    def component_name(self) -> str:
        """Unique identifier for this component."""
        pass

    @abstractmethod
    def check(self) -> ComponentUpdate:
        """
        Check for updates.

        Returns:
            ComponentUpdate with current/available versions.
            If no update available, available_version should be empty or equal to current.
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
                timeout=30,
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)
