"""
Translation tool for A.S.I.S.: ``translate_text``.

Travels the standard path (ToolRegistry -> ToolRouter ->
PermissionManager/authorizer -> ToolExecutor) like every other tool and
delegates to the Translation Engine — never to the network directly.
Translated text is returned as data; it never becomes an instruction.
"""

from __future__ import annotations

from typing import Any

from asis.permissions.models import PermissionLevel
from asis.translation.errors import TranslationError

from ..base import Tool, ToolMetadata
from ..result import ToolResult


def _translation_settings():
    from asis.configuration.settings import settings

    return settings.translation


class TranslateTextTool(Tool):
    """Translate text between supported languages (offline, local model)."""

    metadata = ToolMetadata(
        name="translate_text",
        description=(
            "Translate text into a target language. Returns translated "
            "text plus language metadata."
        ),
        category="translation",
        permission=PermissionLevel.LOW,
        tags=("translation", "language", "local"),
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "target_language": {"type": "string"},
                "source_language": {"type": "string"},
            },
            "required": ["text", "target_language"],
        },
    )

    def __init__(self, engine=None) -> None:
        self._engine = engine

    def _client(self):
        if self._engine is not None:
            return self._engine
        from asis.translation.engine import build_engine_from_settings

        return build_engine_from_settings()

    def execute(self, **kwargs: Any) -> ToolResult:
        settings = _translation_settings()
        if not settings.enabled:
            return ToolResult.failure(
                error="TRANSLATION_DISABLED: translation is disabled "
                "by configuration.",
                tool_name=self.name,
            )
        text = kwargs.get("text", "")
        if not isinstance(text, str) or not text.strip():
            return ToolResult.failure(
                error="'text' must be a non-empty string.",
                tool_name=self.name,
            )
        target = kwargs.get("target_language", "")
        if not isinstance(target, str) or not target.strip():
            return ToolResult.failure(
                error="'target_language' must be a non-empty string.",
                tool_name=self.name,
            )
        source = kwargs.get("source_language")
        if source is None:
            source = settings.default_source
        if not isinstance(source, str) or not source.strip():
            return ToolResult.failure(
                error="'source_language' must be a non-empty string.",
                tool_name=self.name,
            )
        try:
            result = self._client().translate_text(
                text.strip(), target.strip(), source.strip()
            )
        except TranslationError as exc:
            return ToolResult.failure(
                error=f"{exc.code}: {exc.message.split(': ', 1)[-1]}"
                if ": " in exc.message
                else f"{exc.code}: {exc.message}",
                tool_name=self.name,
            )
        except Exception as exc:
            return ToolResult.failure(
                error=f"TRANSLATION_PROVIDER_ERROR: {exc}",
                tool_name=self.name,
            )
        return ToolResult.ok(
            data={
                "source_language": result.source_language,
                "target_language": result.target_language,
                "source_text": result.source_text,
                "translated_text": result.translated_text,
                "provider": result.provider,
                "model": result.model,
                "detected_source": result.detected_source,
                "cached": result.cached,
            },
            tool_name=self.name,
        )


def build_translation_tools(engine=None) -> list[Tool]:
    """Build the translation tools bound to ``engine`` (default if None)."""
    return [TranslateTextTool(engine)]


def register_translation_tools(registry, engine=None) -> list[str]:
    """Register translation tools on ``registry``; returns registered names."""
    names: list[str] = []
    for tool in build_translation_tools(engine):
        registry.register(tool)
        names.append(tool.name)
    return names
