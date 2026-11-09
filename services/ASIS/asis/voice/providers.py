"""
Provider interfaces for the A.S.I.S. voice subsystem.

Engines are replaceable so A.S.I.S. runs without hardware or heavy AI
dependencies in tests. Real providers (faster-whisper, TTS engines,
microphone capture) implement these contracts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import AudioData, SpeakerResult, TranscriptionResult


class AudioInputProvider(ABC):
    """Captures audio from a source."""

    @abstractmethod
    def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def read(self, num_samples: int) -> AudioData:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError


class AudioOutputProvider(ABC):
    """Plays audio to an output."""

    @abstractmethod
    def play(self, audio: AudioData) -> None:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError


class SpeechRecognizer(ABC):
    """Converts audio into text."""

    @abstractmethod
    def transcribe(self, audio: AudioData) -> TranscriptionResult:
        raise NotImplementedError


class SpeakerIdentifier(ABC):
    """Identifies who is speaking."""

    @abstractmethod
    def identify(self, audio: AudioData) -> SpeakerResult:
        raise NotImplementedError


class TextToSpeechProvider(ABC):
    """Converts text into speech audio."""

    @abstractmethod
    def synthesize(self, text: str) -> AudioData:
        raise NotImplementedError

    def stop(self) -> None:
        """Interrupt active speech where supported (no-op by default)."""
        return None


class WakeWordDetector(ABC):
    """Detects a configured wake phrase in audio.

    Concrete engines (e.g. openWakeWord) implement audio inference.
    Text-surface matching lives in ``KeyphraseWakeWordDetector`` and in
    mocks; this interface stays audio-first so the pipeline does not
    depend on a specific engine.
    """

    @property
    @abstractmethod
    def phrases(self) -> tuple[str, ...]:
        raise NotImplementedError

    @abstractmethod
    def detect(self, audio: AudioData) -> bool:
        """Return True when the wake phrase is present in ``audio``."""
        raise NotImplementedError

    def detect_text(self, text: str) -> bool:
        """Optional text-surface fallback; default checks phrase prefix."""
        normalized = text.strip().casefold()
        return any(normalized.startswith(p) for p in self.phrases)


class SpeakerEmbeddingProvider(ABC):
    """Extracts a speaker embedding vector from audio.

    Returns a plain ``list[float]`` so embeddings stay serializable
    without a numpy/torch dependency in the interface.
    """

    @abstractmethod
    def embed(self, audio: AudioData) -> list[float]:
        """Extract an embedding vector from ``audio``."""
        raise NotImplementedError


class VadDetector(ABC):
    """Detects voice activity in audio.

    Lightweight gate before wake-word/STT so silence does not trigger
    expensive inference. Implementations must not require hardware.
    """

    @abstractmethod
    def is_speech(self, audio: AudioData) -> bool:
        """Return True when ``audio`` likely contains speech."""
        raise NotImplementedError
