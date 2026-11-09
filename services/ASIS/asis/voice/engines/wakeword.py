"""
Wake word detection for A.S.I.S.

Text-surface detection so the voice pipeline can decide whether a
transcription started with a configured wake phrase. No audio model
required; hotword model integration belongs to a future milestone.
"""

from __future__ import annotations

from collections.abc import Iterable


class KeyphraseWakeWordDetector:
    """Detects configured wake phrases in transcribed text."""

    def __init__(
        self,
        phrases: Iterable[str] = ("hey asis",),
    ) -> None:
        self._phrases = {
            phrase.strip().casefold() for phrase in phrases if phrase.strip()
        }

    @property
    def phrases(self) -> tuple[str, ...]:
        return tuple(self._phrases)

    def detect(self, text: str) -> bool:
        """Return whether the text starts with a wake phrase."""
        normalized = text.strip().casefold()
        return any(normalized.startswith(phrase) for phrase in self._phrases)

    def strip_phrase(self, text: str) -> str:
        """Remove a leading wake phrase and return the remainder."""
        normalized = text.strip()

        for phrase in self._phrases:
            if normalized.casefold().startswith(phrase):
                return normalized[len(phrase) :].strip()

        return normalized
