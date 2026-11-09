"""Deterministic mock voice engines for development and tests.

Scriptable: preload transcripts/audio, then assert what was captured or
played. No hardware, no ML libraries, no network.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping

from .providers import (
    AudioFrame,
    SpeechInput,
    SpeechOutput,
    Transcriber,
    Transcript,
    Vocalizer,
    VoiceError,
)


def _check_timeout(timeout_s: float | None) -> None:
    if timeout_s is None:
        return
    if (
        isinstance(timeout_s, bool)
        or not isinstance(timeout_s, (int, float))
        or not timeout_s > 0
    ):
        raise VoiceError("timeout_s must be a positive number of seconds")


class MockSpeechInput(SpeechInput):
    """Replays preloaded frames; records nothing."""

    def __init__(self, frames: list[AudioFrame] | None = None) -> None:
        self._frames: deque[AudioFrame] = deque(frames or [])

    def queue(self, frame: AudioFrame) -> None:
        """Stage a frame for the next :meth:`listen` call."""
        self._frames.append(frame)

    def listen(self, *, timeout_s: float | None = None) -> AudioFrame:
        _check_timeout(timeout_s)
        if not self._frames:
            raise VoiceError("no audio available")
        return self._frames.popleft()


class MockTranscriber(Transcriber):
    """Maps audio to fixed text (by metadata tag or default)."""

    def __init__(
        self, default_text: str = "", *, mapping: Mapping[str, str] | None = None
    ) -> None:
        self._default = default_text
        self._mapping = dict(mapping or {})
        self.calls: list[AudioFrame] = []

    def transcribe(
        self, frame: AudioFrame, *, timeout_s: float | None = None
    ) -> Transcript:
        _check_timeout(timeout_s)
        self.calls.append(frame)
        tag = frame.metadata.get("tag")
        text = self._mapping.get(tag, self._default) if tag else self._default
        if not text:
            raise VoiceError("could not transcribe audio")
        return Transcript(text=text, confidence=1.0)


class MockVocalizer(Vocalizer):
    """Turns text into marker frames; records every call."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def vocalize(
        self, text: str, *, timeout_s: float | None = None
    ) -> AudioFrame:
        _check_timeout(timeout_s)
        if not (isinstance(text, str) and text.strip()):
            raise VoiceError("cannot vocalize empty text")
        self.calls.append(text)
        return AudioFrame(samples=(0.0,), metadata={"text": text})


class MockSpeechOutput(SpeechOutput):
    """Collects played frames for assertions."""

    def __init__(self, *, fail: bool = False) -> None:
        self.played: list[AudioFrame] = []
        self._fail = fail

    def play(self, frame: AudioFrame, *, timeout_s: float | None = None) -> None:
        _check_timeout(timeout_s)
        if self._fail:
            raise VoiceError("output device unavailable")
        self.played.append(frame)
