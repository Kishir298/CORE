"""Translation tool for T.I.V.I.S.S.: translate_text.

Translates text between supported languages (offline, local model).
Returns translated text plus language metadata.
"""

from __future__ import annotations

from typing import Any

from ..configuration import settings as tiviss_settings
from ..permissions.permissions import Permission
from .interface import Tool, ToolError, ToolResult, ToolStatus


def _translation_settings():
    return tiviss_settings.translation


class TranslateTextTool(Tool):
    """Translate text into a target language. Returns translated
            text plus language metadata."""

    @property
    def tool_id(self) -> str:
        return "translate_text"

    @property
    def name(self) -> str:
        return "TranslateText"

    @property
    def description(self) -> str:
        return "Translate text into a target language. Returns translated text plus language metadata."

    @property
    def permission(self) -> Permission:
        return Permission.of("tools.translation")

    def __init__(self, engine=None) -> None:
        self._engine = engine

    def _client(self):
        if self._engine is not None:
            return self._engine
        from tiviss.translation.engine import build_engine_from_settings

        return build_engine_from_settings()

    def validate_input(self, params: dict[str, Any]) -> dict[str, Any]:
        if "text" not in params:
            raise ToolError("text must be provided")
        text = params.get("text", "")
        if not isinstance(text, str) or not text.strip():
            raise ToolError("text must be a non-empty string")
        if "target_language" not in params:
            raise ToolError("target_language must be provided")
        target = params.get("target_language", "")
        if not isinstance(target, str) or not target.strip():
            raise ToolError("target_language must be a non-empty string")
        source = params.get("source_language")
        if source is None:
            source = _translation_settings().default_source
        if not isinstance(source, str) or not source.strip():
            raise ToolError("source_language must be a non-empty string")
        return {"text": text.strip(), "target_language": target.strip(), "source_language": source.strip()}

    def execute(self, params: dict[str, Any]) -> ToolResult:
        trans_settings = _translation_settings()
        if not trans_settings.enabled:
            return ToolResult(
                tool_id=self.tool_id,
                status=ToolStatus.FAILED,
                error="TRANSLATION_DISABLED: translation is disabled by configuration.",
            )

        validated = self.validate_input(params)
        try:
            result = self._client().translate_text(
                validated["text"],
                validated["target_language"],
                validated["source_language"]
            )
        except Exception as exc:
            code = getattr(exc, "code", None)
            message = getattr(exc, "message", None) or str(exc) or "translation failed"
            if code:
                tail = message.split(": ", 1)[-1] if ": " in message else message
                return ToolResult(
                    tool_id=self.tool_id,
                    status=ToolStatus.FAILED,
                    error=f"{code}: {tail}",
                )
            return ToolResult(
                tool_id=self.tool_id,
                status=ToolStatus.FAILED,
                error=f"TRANSLATION_PROVIDER_ERROR: {message}",
            )

        return ToolResult(
            tool_id=self.tool_id,
            status=ToolStatus.OK,
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
        )


def build_translation_tools(engine=None) -> list[Tool]:
    """Build the translation tools bound to engine (default if None)."""
    return [TranslateTextTool(engine)]


def register_translation_tools(registry, engine=None) -> list[str]:
    """Register translation tools on registry; returns registered names."""
    names: list[str] = []
    for tool in build_translation_tools(engine):
        registry.register(tool)
        names.append(tool.tool_id)
    return names