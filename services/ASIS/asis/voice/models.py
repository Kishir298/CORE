"""
Data models for the A.S.I.S. voice subsystem.

Canonical models live here only. Other voice modules must import from
this file instead of defining their own ``AudioData``,
``TranscriptionResult`` or ``SpeakerResult``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from asis.events.events import Event, EventType


@dataclass(frozen=True)
class AudioData:
    """A captured or synthesized audio segment."""

    samples: Any
    sample_rate: int = 16_000
    channels: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.sample_rate, int) or self.sample_rate <= 0:
            raise ValueError("sample_rate must be a positive int.")
        if not isinstance(self.channels, int) or self.channels <= 0:
            raise ValueError("channels must be a positive int.")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dict.")


@dataclass(frozen=True)
class TranscriptionResult:
    """Result returned by a speech-to-text engine."""

    text: str
    language: str | None = None
    confidence: float | None = None
    duration: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise ValueError("text must be a str.")
        if self.language is not None and not isinstance(self.language, str):
            raise ValueError("language must be a str or None.")
        if self.confidence is not None and not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0.")
        if self.duration is not None and float(self.duration) < 0.0:
            raise ValueError("duration must be >= 0.")


@dataclass(frozen=True)
class SpeakerResult:
    """Result returned by a speaker identification engine."""

    speaker_id: str
    confidence: float | None = None
    is_known: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.speaker_id, str) or not self.speaker_id.strip():
            raise ValueError("speaker_id must be a non-empty str.")
        if self.confidence is not None and not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0.")
        if not isinstance(self.is_known, bool):
            raise ValueError("is_known must be a bool.")


@dataclass(frozen=True)
class VoiceEvent:
    """Canonical voice event, compatible with the existing event bus.

    ``event_type`` uses the shared :class:`EventType` vocabulary so voice
    events flow through the existing :class:`EventBus` without a second
    event system. Raw audio is never stored in ``payload``.
    """

    event_type: EventType
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: str = "voice"
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, EventType):
            raise ValueError("event_type must be an EventType.")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be a datetime.")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be a non-empty str.")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dict.")

    def to_event(self) -> Event:
        """Convert to the shared bus :class:`Event` type."""
        return Event(
            type=self.event_type,
            data=dict(self.payload),
            timestamp=self.timestamp,
            source=self.source,
        )

    @classmethod
    def from_event(cls, event: Event) -> VoiceEvent:
        """Build a :class:`VoiceEvent` from a bus :class:`Event`."""
        return cls(
            event_type=event.type,
            timestamp=event.timestamp,
            source=event.source,
            payload=dict(event.data),
        )
