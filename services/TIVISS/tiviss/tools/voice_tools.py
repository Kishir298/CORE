"""Voice tools for T.I.V.I.S.S.: voice_listen, voice_speak, voice_status."""

from __future__ import annotations

from typing import Any

from ..configuration import settings as tiviss_settings
from ..permissions.permissions import Permission
from .interface import Tool, ToolError, ToolResult, ToolStatus


def _voice_settings():
    return tiviss_settings.voice


def _disabled_result(tool_name: str) -> ToolResult:
    return ToolResult(
        tool_id=tool_name,
        status=ToolStatus.FAILED,
        error="VOICE_DISABLED: voice is disabled by configuration.",
    )


class VoiceListenTool(Tool):
    """Listen for voice input and return transcribed text."""

    @property
    def tool_id(self) -> str:
        return "voice_listen"

    @property
    def name(self) -> str:
        return "VoiceListen"

    @property
    def description(self) -> str:
        return "Listen for voice input using STT. Returns transcribed text and confidence."

    @property
    def permission(self) -> Permission:
        return Permission.of("tools.voice")

    def __init__(self, pipeline=None) -> None:
        self._pipeline = pipeline

    def _client(self):
        if self._pipeline is not None:
            return self._pipeline
        from tiviss.voice.pipeline import build_voice_pipeline

        return build_voice_pipeline()

    def validate_input(self, params: dict[str, Any]) -> dict[str, Any]:
        voice = _voice_settings()
        if not voice.enabled:
            raise ToolError("VOICE_DISABLED: voice is disabled by configuration.")
        timeout = params.get("timeout", voice.max_utterance_s)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ToolError("timeout must be a number.")
        return {"timeout": max(1, min(timeout, voice.max_utterance_s))}

    def execute(self, params: dict[str, Any]) -> ToolResult:
        validated = self.validate_input(params)
        try:
            result = self._client().listen(validated["timeout"])
        except Exception as exc:
            code = getattr(exc, "code", None)
            message = getattr(exc, "message", None) or str(exc) or "listen failed."
            if code:
                return ToolResult(
                    tool_id=self.tool_id,
                    status=ToolStatus.FAILED,
                    error=f"{code}: {message.split(': ', 1)[-1]}" if ": " in message else f"{code}: {message}",
                )
            return ToolResult(
                tool_id=self.tool_id,
                status=ToolStatus.FAILED,
                error=f"VOICE_PROVIDER_ERROR: {message}",
            )
        return ToolResult(
            tool_id=self.tool_id,
            status=ToolStatus.OK,
            data={"transcription": result.text, "confidence": result.confidence, "duration": result.duration},
        )


class VoiceSpeakTool(Tool):
    """Speak text using TTS."""

    @property
    def tool_id(self) -> str:
        return "voice_speak"

    @property
    def name(self) -> str:
        return "VoiceSpeak"

    @property
    def description(self) -> str:
        return "Convert text to speech using TTS. Returns audio metadata."

    @property
    def permission(self) -> Permission:
        return Permission.of("tools.voice")

    def __init__(self, pipeline=None) -> None:
        self._pipeline = pipeline

    def _client(self):
        if self._pipeline is not None:
            return self._pipeline
        from tiviss.voice.pipeline import build_voice_pipeline

        return build_voice_pipeline()

    def validate_input(self, params: dict[str, Any]) -> dict[str, Any]:
        voice = _voice_settings()
        if not voice.enabled:
            raise ToolError("VOICE_DISABLED: voice is disabled by configuration.")
        text = params.get("text", "")
        if not isinstance(text, str) or not text.strip():
            raise ToolError("text must be a non-empty string.")
        return {"text": text.strip()}

    def execute(self, params: dict[str, Any]) -> ToolResult:
        validated = self.validate_input(params)
        try:
            result = self._client().speak(validated["text"])
        except Exception as exc:
            code = getattr(exc, "code", None)
            message = getattr(exc, "message", None) or str(exc) or "speak failed."
            if code:
                return ToolResult(
                    tool_id=self.tool_id,
                    status=ToolStatus.FAILED,
                    error=f"{code}: {message.split(': ', 1)[-1]}" if ": " in message else f"{code}: {message}",
                )
            return ToolResult(
                tool_id=self.tool_id,
                status=ToolStatus.FAILED,
                error=f"VOICE_PROVIDER_ERROR: {message}",
            )
        return ToolResult(
            tool_id=self.tool_id,
            status=ToolStatus.OK,
            data={"audio_format": result.format, "duration": result.duration, "size": result.size},
        )


class VoiceStatusTool(Tool):
    """Check voice pipeline status."""

    @property
    def tool_id(self) -> str:
        return "voice_status"

    @property
    def name(self) -> str:
        return "VoiceStatus"

    @property
    def description(self) -> str:
        return "Check voice pipeline status (STT, TTS, VAD, speaker identification)."

    @property
    def permission(self) -> Permission:
        return Permission.of("tools.safe")

    def __init__(self, pipeline=None) -> None:
        self._pipeline = pipeline

    def _client(self):
        if self._pipeline is not None:
            return self._pipeline
        from tiviss.voice.pipeline import build_voice_pipeline

        return build_voice_pipeline()

    def validate_input(self, params: dict[str, Any]) -> dict[str, Any]:
        voice = _voice_settings()
        if not voice.enabled:
            raise ToolError("VOICE_DISABLED: voice is disabled by configuration.")
        return {}

    def execute(self, params: dict[str, Any]) -> ToolResult:
        self.validate_input(params)
        try:
            result = self._client().status()
        except Exception as exc:
            code = getattr(exc, "code", None)
            message = getattr(exc, "message", None) or str(exc) or "status failed."
            if code:
                return ToolResult(
                    tool_id=self.tool_id,
                    status=ToolStatus.FAILED,
                    error=f"{code}: {message.split(': ', 1)[-1]}" if ": " in message else f"{code}: {message}",
                )
            return ToolResult(
                tool_id=self.tool_id,
                status=ToolStatus.FAILED,
                error=f"VOICE_PROVIDER_ERROR: {message}",
            )
        return ToolResult(
            tool_id=self.tool_id,
            status=ToolStatus.OK,
            data={"stt": result.stt, "tts": result.tts, "vad": result.vad, "speaker": result.speaker, "pipeline": result.pipeline},
        )


def build_voice_tools(pipeline=None) -> list[Tool]:
    """Build the voice tools bound to pipeline (default if None)."""
    return [VoiceListenTool(pipeline), VoiceSpeakTool(pipeline), VoiceStatusTool(pipeline)]


def register_voice_tools(registry, pipeline=None) -> list[str]:
    """Register voice tools on registry; returns the registered names."""
    names: list[str] = []
    for tool in build_voice_tools(pipeline):
        registry.register(tool)
        names.append(tool.tool_id)
    return names