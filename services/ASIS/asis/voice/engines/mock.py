"""
Mock voice engines for A.S.I.S.

Used by tests and as a zero-dependency fallback. Each mock is scriptable
so pipeline behavior can be verified without audio hardware.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..models import AudioData, SpeakerResult, TranscriptionResult
from ..providers import (
    AudioInputProvider,
    AudioOutputProvider,
    SpeakerEmbeddingProvider,
    SpeakerIdentifier,
    SpeechRecognizer,
    TextToSpeechProvider,
    VadDetector,
    WakeWordDetector,
)


class MockAudioInput(AudioInputProvider):
    """Yields scripted audio segments."""

    def __init__(self, segments: Iterable[AudioData] = ()) -> None:
        self._segments = list(segments)
        self._index = 0
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True
        self.stopped = False

    def read(self, num_samples: int) -> AudioData:
        if self._index >= len(self._segments):
            return AudioData(samples=[])

        segment = self._segments[self._index]
        self._index += 1
        return segment

    def stop(self) -> None:
        self.stopped = True


class MockAudioOutput(AudioOutputProvider):
    """Records played audio; never touches a sound device."""

    def __init__(self) -> None:
        self.played: list[AudioData] = []
        self.stopped = False

    def play(self, audio: AudioData) -> None:
        self.played.append(audio)

    def stop(self) -> None:
        self.stopped = True


class MockSpeechRecognizer(SpeechRecognizer):
    """Returns a scripted transcription."""

    def __init__(
        self,
        text: str = "",
        language: str | None = "en",
        confidence: float | None = 0.95,
    ) -> None:
        self._text = text
        self._language = language
        self._confidence = confidence
        self.transcribed: list[AudioData] = []

    def transcribe(self, audio: AudioData) -> TranscriptionResult:
        self.transcribed.append(audio)

        return TranscriptionResult(
            text=self._text,
            language=self._language,
            confidence=self._confidence,
        )


class MockSpeakerIdentifier(SpeakerIdentifier):
    """Returns a scripted speaker."""

    def __init__(
        self,
        speaker_id: str = "unknown",
        confidence: float | None = None,
        is_known: bool = False,
    ) -> None:
        self._speaker_id = speaker_id
        self._confidence = confidence
        self._is_known = is_known
        self.identified: list[AudioData] = []

    def identify(self, audio: AudioData) -> SpeakerResult:
        self.identified.append(audio)

        return SpeakerResult(
            speaker_id=self._speaker_id,
            confidence=self._confidence,
            is_known=self._is_known,
        )


class MockTextToSpeech(TextToSpeechProvider):
    """Captures synthesized text and returns a mock audio segment."""

    def __init__(self, sample_rate: int = 16_000) -> None:
        self._sample_rate = sample_rate
        self.synthesized: list[str] = []
        self.stopped = False

    def synthesize(self, text: str) -> AudioData:
        self.synthesized.append(text)

        return AudioData(
            samples=[0, 0, 0],
            sample_rate=self._sample_rate,
        )

    def stop(self) -> None:
        self.stopped = True


class MockWakeWordDetector(WakeWordDetector):
    """Scriptable wake-word detector; no audio model required."""

    def __init__(
        self,
        phrases: Iterable[str] = ("hey asis",),
        results: Iterable[bool] | None = None,
        default: bool = True,
    ) -> None:
        self._phrases = tuple(
            {p.strip().casefold() for p in phrases if p.strip()} or {"hey asis"}
        )
        self._results = list(results) if results is not None else []
        self._default = default
        self.checked: list[AudioData] = []

    @property
    def phrases(self) -> tuple[str, ...]:
        return self._phrases

    def detect(self, audio: AudioData) -> bool:
        self.checked.append(audio)
        if self._results:
            return bool(self._results.pop(0))
        return bool(self._default)


class MockSpeakerEmbeddingProvider(SpeakerEmbeddingProvider):
    """Deterministic embedding provider for tests."""

    def __init__(self, embedding: list[float] | None = None) -> None:
        self._embedding = list(embedding) if embedding is not None else [1.0, 0.0, 0.0]
        self.embedded: list[AudioData] = []

    def embed(self, audio: AudioData) -> list[float]:
        self.embedded.append(audio)
        return list(self._embedding)


class MockVadDetector(VadDetector):
    """Scriptable VAD; defaults to speech present."""

    def __init__(
        self,
        results: Iterable[bool] | None = None,
        default: bool = True,
    ) -> None:
        self._results = list(results) if results is not None else []
        self._default = default
        self.checked: list[AudioData] = []

    def is_speech(self, audio: AudioData) -> bool:
        self.checked.append(audio)
        if self._results:
            return bool(self._results.pop(0))
        return bool(self._default)
