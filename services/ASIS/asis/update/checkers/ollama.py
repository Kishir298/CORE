"""
Ollama model update checker for ASIS.
"""

from __future__ import annotations

import json

from . import BaseChecker, ComponentUpdate


class OllamaModelChecker(BaseChecker):
    """Checks for Ollama model updates."""

    @property
    def component_name(self) -> str:
        return "ollama_models"

    def __init__(self, model: str | None = None):
        """
        Initialize checker.

        Args:
            model: Specific model to check (e.g., "qwen3:14b").
                   If None, checks all locally installed models.
        """
        self._model = model

    def check(self) -> ComponentUpdate:
        """Check for Ollama model updates."""
        try:
            # Check if ollama is available
            returncode, stdout, stderr = self._run_command(["ollama", "list", "--format", "json"])
            if returncode != 0:
                return ComponentUpdate(
                    component="ollama_models",
                    current_version="unavailable",
                    available_version="",
                    description=f"Ollama not available: {stderr}",
                )

            try:
                models = json.loads(stdout) if stdout.strip() else []
            except json.JSONDecodeError:
                return ComponentUpdate(
                    component="ollama_models",
                    current_version="error",
                    available_version="",
                    description="Failed to parse ollama list output",
                )

            if not models:
                return ComponentUpdate(
                    component="ollama_models",
                    current_version="none",
                    available_version="",
                    description="No models installed locally",
                )

            # Filter to specific model if configured
            if self._model:
                models = [m for m in models if m.get("name", "").startswith(self._model.split(":")[0])]

            if not models:
                return ComponentUpdate(
                    component="ollama_models",
                    current_version="not found",
                    available_version="",
                    description=f"Model '{self._model}' not installed locally",
                )

            # For now, just report current models
            # Real update checking would require querying Ollama registry
            model_names = [m.get("name", "unknown") for m in models]
            return ComponentUpdate(
                component="ollama_models",
                current_version=f"{len(models)} installed",
                available_version="check registry",
                description=f"Installed: {', '.join(model_names)}. Run 'ollama pull' to update.",
                install_command=f"ollama pull {self._model}" if self._model else "ollama pull <model>",
                metadata={"models": model_names},
            )

        except Exception as e:
            return ComponentUpdate(
                component="ollama_models",
                current_version="error",
                available_version="",
                description=f"Ollama check failed: {e}",
            )
