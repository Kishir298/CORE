"""
Standard A.S.I.S. events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    """Known A.S.I.S. event types."""

    SYSTEM_STARTED = "system.started"
    SYSTEM_READY = "system.ready"
    SYSTEM_STOPPING = "system.stopping"
    SYSTEM_STOPPED = "system.stopped"
    SYSTEM_FAILED = "system.failed"

    MODEL_LOADING = "model.loading"
    MODEL_LOADED = "model.loaded"
    MODEL_UNAVAILABLE = "model.unavailable"

    AI_INFERENCE_STARTED = "ai.inference.started"
    AI_INFERENCE_FINISHED = "ai.inference.finished"
    AI_INFERENCE_FAILED = "ai.inference.failed"
    AI_INFERENCE_CANCELLED = "ai.inference.cancelled"

    TOOL_EXECUTION_STARTED = "tool.execution.started"
    TOOL_EXECUTION_FINISHED = "tool.execution.finished"
    TOOL_EXECUTION_FAILED = "tool.execution.failed"
    TOOL_DENIED = "tool.denied"

    MEMORY_SAVED = "memory.saved"
    MEMORY_DELETED = "memory.deleted"
    MEMORY_CLEARED = "memory.cleared"

    VOICE_INPUT = "voice.input"
    VOICE_VAD = "voice.vad"
    VOICE_STT_STARTED = "voice.stt.started"
    VOICE_STT_READY = "voice.stt.ready"
    VOICE_SPEAKER_IDENTIFIED = "voice.speaker.identified"
    VOICE_WAKE_WORD_DETECTED = "voice.wake_word.detected"
    VOICE_ASSISTANT_STARTED = "voice.assistant.started"
    VOICE_ASSISTANT_FINISHED = "voice.assistant.finished"
    VOICE_TTS_STARTED = "voice.tts.started"
    VOICE_TTS_FINISHED = "voice.tts.finished"
    VOICE_OUTPUT = "voice.output"
    VOICE_INTERRUPTED = "voice.interrupted"
    VOICE_ERROR = "voice.error"
    VOICE_STOPPED = "voice.stopped"

    INTERRUPT_REQUESTED = "interrupt.requested"
    INTERRUPT_CANCELLED = "interrupt.cancelled"

    ERROR_OCCURRED = "error.occurred"


@dataclass(frozen=True)
class Event:
    """A message sent through the A.S.I.S. event bus."""

    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: str = "unknown"
