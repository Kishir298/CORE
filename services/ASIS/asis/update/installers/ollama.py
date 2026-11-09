"""
Ollama model update installer for ASIS.
"""

from __future__ import annotations

from . import BaseInstaller, InstallResult


class OllamaModelInstaller(BaseInstaller):
    """Installs Ollama model updates."""

    @property
    def component_name(self) -> str:
        return "ollama_models"

    def __init__(self, model: str | None = None):
        """
        Initialize installer.

        Args:
            model: Specific model to update (e.g., "qwen3:14b").
                   If None, attempts to update all locally installed models.
        """
        self._model = model

    def install(self, update_info: dict) -> InstallResult:
        """Pull updated Ollama model(s)."""
        try:
            if self._model:
                return self._pull_model(self._model)
            else:
                # Update all installed models
                return self._pull_all_models()
        except Exception as e:
            return InstallResult(
                component="ollama_models",
                success=False,
                message=f"Ollama install failed: {e}",
            )

    def _pull_model(self, model: str) -> InstallResult:
        """Pull a specific model."""
        returncode, stdout, stderr = self._run_command(["ollama", "pull", model])

        if returncode != 0:
            return InstallResult(
                component="ollama_models",
                success=False,
                message=f"Failed to pull {model}: {stderr}",
                details={"model": model, "stderr": stderr},
            )

        return InstallResult(
            component="ollama_models",
            success=True,
            message=f"Updated {model}",
            requires_restart=False,  # Models loaded on demand
            details={"model": model},
        )

    def _pull_all_models(self) -> InstallResult:
        """Pull all locally installed models."""
        # First, list installed models
        returncode, stdout, stderr = self._run_command(["ollama", "list", "--format", "json"])
        if returncode != 0:
            return InstallResult(
                component="ollama_models",
                success=False,
                message=f"Failed to list models: {stderr}",
            )

        import json
        try:
            models = json.loads(stdout) if stdout.strip() else []
        except json.JSONDecodeError:
            return InstallResult(
                component="ollama_models",
                success=False,
                message="Failed to parse model list",
            )

        if not models:
            return InstallResult(
                component="ollama_models",
                success=True,
                message="No models to update",
            )

        results = []
        for model_info in models:
            name = model_info.get("name", "")
            if name:
                result = self._pull_model(name)
                results.append({"model": name, "success": result.success, "message": result.message})

        failed = [r for r in results if not r["success"]]
        if failed:
            return InstallResult(
                component="ollama_models",
                success=False,
                message=f"Failed to update {len(failed)} of {len(results)} models",
                details={"results": results},
            )

        return InstallResult(
            component="ollama_models",
            success=True,
            message=f"Updated {len(results)} model(s)",
            details={"results": results},
        )
