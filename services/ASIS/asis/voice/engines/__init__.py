"""
A.S.I.S. voice engines.
"""

from .mock import (
    MockAudioInput,
    MockAudioOutput,
    MockSpeakerEmbeddingProvider,
    MockSpeakerIdentifier,
    MockSpeechRecognizer,
    MockTextToSpeech,
    MockVadDetector,
    MockWakeWordDetector,
)
from .wakeword import KeyphraseWakeWordDetector

try:  # optional heavy dep; never break base imports
    from .openwakeword import OpenWakeWordDetector
except Exception:  # pragma: no cover - missing optional dep
    OpenWakeWordDetector = None  # type: ignore[assignment]

__all__ = [
    "KeyphraseWakeWordDetector",
    "MockAudioInput",
    "MockAudioOutput",
    "MockSpeakerEmbeddingProvider",
    "MockSpeakerIdentifier",
    "MockSpeechRecognizer",
    "MockTextToSpeech",
    "MockVadDetector",
    "MockWakeWordDetector",
    "OpenWakeWordDetector",
]
