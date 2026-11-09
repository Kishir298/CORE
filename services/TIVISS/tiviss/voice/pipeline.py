"""Voice pipeline for T.I.V.I.S.S."""

from __future__ import annotations

from dataclasses import dataclass

from ..configuration import settings as tiviss_settings


def _voice_settings():
    return tiviss_settings.voice


@dataclass
class ListenResult:
    text: str
    confidence: float
    duration: float


@dataclass
class SpeakResult:
    format: str
    duration: float
    size: int


@dataclass
class StatusResult:
    stt: str
    tts: str
    vad: str
    speaker: str
    pipeline: str


class VoicePipeline:
    """Voice pipeline with STT, TTS, VAD, and speaker identification."""

    def __init__(self):
        self._settings = _voice_settings()
        self._initialized = False

    def _ensure_initialized(self):
        if not self._initialized:
            # For now, mock initialization
            self._initialized = True

    def listen(self, timeout: float) -> ListenResult:
        self._ensure_initialized()
        if not self._settings.enabled:
            raise Exception("VOICE_DISABLED: voice is disabled by configuration.")
        # Mock implementation - returns empty transcription
        return ListenResult(text="", confidence=0.0, duration=0.0)

    def speak(self, text: str) -> SpeakResult:
        self._ensure_initialized()
        if not self._settings.enabled:
            raise Exception("VOICE_DISABLED: voice is disabled by configuration.")
        # Mock implementation
        return SpeakResult(format="wav", duration=0.0, size=0)

    def status(self) -> StatusResult:
        self._ensure_initialized()
        return StatusResult(
            stt="mock",
            tts="mock",
            vad="mock",
            speaker="mock",
            pipeline="mock"
        )


def build_voice_pipeline() -> VoicePipeline:
    """Build the voice pipeline (default if None)."""
    return VoicePipeline()
