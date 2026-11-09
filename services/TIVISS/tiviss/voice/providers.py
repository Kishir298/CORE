"""Voice provider interfaces.

Four replaceable stages: capture audio (input), transcribe to text,
vocalize text to audio (output). Transcription and vocalization are split
from capture/playback so each can be mocked or swapped independently.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


class VoiceError(RuntimeError):
    """Raised when a voice stage cannot fulfill a request."""


@dataclass(frozen=True)
class AudioFrame:
    """One chunk of PCM audio with its sample rate."""

    samples: tuple[float, ...] = ()
    sample_rate: int = 16000
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Transcript:
    """Text produced from audio, with an optional confidence score."""

    text: str
    confidence: float = 1.0


class SpeechInput(ABC):
    """Capture audio frames from a source (microphone, file, test)."""

    @abstractmethod
    def listen(self, *, timeout_s: float | None = None) -> AudioFrame:
        """Capture one utterance. Raises :class:`VoiceError` on failure."""


class Transcriber(ABC):
    """Convert audio frames to text."""

    @abstractmethod
    def transcribe(
        self, frame: AudioFrame, *, timeout_s: float | None = None
    ) -> Transcript:
        """Transcribe ``frame``. Raises :class:`VoiceError` on failure."""


class Vocalizer(ABC):
    """Convert text to audio frames."""

    @abstractmethod
    def vocalize(
        self, text: str, *, timeout_s: float | None = None
    ) -> AudioFrame:
        """Vocalize ``text``. Raises :class:`VoiceError` on failure."""


class SpeechOutput(ABC):
    """Play audio frames to a sink (speaker, file, test)."""

    @abstractmethod
    def play(self, frame: AudioFrame, *, timeout_s: float | None = None) -> None:
        """Play ``frame``. Raises :class:`VoiceError` on failure."""
