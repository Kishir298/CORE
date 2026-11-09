"""A.S.I.S. TUI event bridge.

Subscribes to the A.S.I.S. EventBus and maps events to AppState mutations.
This is the single integration point between backend events and UI state.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from asis.events.bus import EventBus
from asis.events.events import Event, EventType
from asis.tui.state import (
    AppState,
    VoiceState,
)


@dataclass
class EventMapping:
    """Maps an EventType to a state mutation function."""
    event_type: EventType
    handler: Callable[[Event, AppState], None]


class EventBridge:
    """Bridges A.S.I.S. EventBus to TUI AppState."""

    def __init__(self, state: AppState, event_bus: EventBus | None = None):
        self.state = state
        self.event_bus = event_bus
        self._subscriptions: list[tuple[EventType, Callable]] = []
        self._lock = threading.Lock()
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register all event handlers."""
        mappings = [
            # System events
            EventMapping(EventType.SYSTEM_STARTED, self._on_system_started),
            EventMapping(EventType.SYSTEM_READY, self._on_system_ready),
            EventMapping(EventType.SYSTEM_STOPPING, self._on_system_stopping),
            EventMapping(EventType.SYSTEM_STOPPED, self._on_system_stopped),
            EventMapping(EventType.SYSTEM_FAILED, self._on_system_failed),

            # Model events
            EventMapping(EventType.MODEL_LOADING, self._on_model_loading),
            EventMapping(EventType.MODEL_LOADED, self._on_model_loaded),
            EventMapping(EventType.MODEL_UNAVAILABLE, self._on_model_unavailable),

            # AI inference events
            EventMapping(EventType.AI_INFERENCE_STARTED, self._on_inference_started),
            EventMapping(EventType.AI_INFERENCE_FINISHED, self._on_inference_finished),
            EventMapping(EventType.AI_INFERENCE_FAILED, self._on_inference_failed),
            EventMapping(EventType.AI_INFERENCE_CANCELLED, self._on_inference_cancelled),

            # Tool events
            EventMapping(EventType.TOOL_EXECUTION_STARTED, self._on_tool_started),
            EventMapping(EventType.TOOL_EXECUTION_FINISHED, self._on_tool_finished),
            EventMapping(EventType.TOOL_EXECUTION_FAILED, self._on_tool_failed),
            EventMapping(EventType.TOOL_DENIED, self._on_tool_denied),

            # Memory events
            EventMapping(EventType.MEMORY_SAVED, self._on_memory_saved),
            EventMapping(EventType.MEMORY_DELETED, self._on_memory_deleted),
            EventMapping(EventType.MEMORY_CLEARED, self._on_memory_cleared),

            # Voice events
            EventMapping(EventType.VOICE_INPUT, self._on_voice_input),
            EventMapping(EventType.VOICE_VAD, self._on_voice_vad),
            EventMapping(EventType.VOICE_STT_STARTED, self._on_voice_stt_started),
            EventMapping(EventType.VOICE_STT_READY, self._on_voice_stt_ready),
            EventMapping(EventType.VOICE_SPEAKER_IDENTIFIED, self._on_voice_speaker_identified),
            EventMapping(EventType.VOICE_WAKE_WORD_DETECTED, self._on_voice_wake_word),
            EventMapping(EventType.VOICE_ASSISTANT_STARTED, self._on_voice_assistant_started),
            EventMapping(EventType.VOICE_ASSISTANT_FINISHED, self._on_voice_assistant_finished),
            EventMapping(EventType.VOICE_TTS_STARTED, self._on_voice_tts_started),
            EventMapping(EventType.VOICE_TTS_FINISHED, self._on_voice_tts_finished),
            EventMapping(EventType.VOICE_OUTPUT, self._on_voice_output),
            EventMapping(EventType.VOICE_INTERRUPTED, self._on_voice_interrupted),
            EventMapping(EventType.VOICE_ERROR, self._on_voice_error),
            EventMapping(EventType.VOICE_STOPPED, self._on_voice_stopped),

            # Interrupt events
            EventMapping(EventType.INTERRUPT_REQUESTED, self._on_interrupt_requested),
            EventMapping(EventType.INTERRUPT_CANCELLED, self._on_interrupt_cancelled),

            # Error events
            EventMapping(EventType.ERROR_OCCURRED, self._on_error_occurred),
        ]

        for mapping in mappings:
            self._subscribe(mapping.event_type, mapping.handler)

    def _subscribe(self, event_type: EventType, handler: Callable[[Event, AppState], None]) -> None:
        """Subscribe to an event type."""
        if self.event_bus is None:
            return

        def wrapper(event: Event) -> None:
            try:
                handler(event, self.state)
            except Exception:
                # Never let event handling crash the UI
                pass

        self.event_bus.subscribe(event_type, wrapper)
        with self._lock:
            self._subscriptions.append((event_type, wrapper))

    def unsubscribe_all(self) -> None:
        """Unsubscribe from all events."""
        if self.event_bus is None:
            return
        with self._lock:
            for event_type, wrapper in self._subscriptions:
                with __import__("contextlib").suppress(Exception):
                    self.event_bus.unsubscribe(event_type, wrapper)
            self._subscriptions.clear()

    # --- System handlers ---
    def _on_system_started(self, event: Event, state: AppState) -> None:
        state.add_boot_log("BOOT", "Starting A.S.I.S.")

    def _on_system_ready(self, event: Event, state: AppState) -> None:
        state.add_boot_log("OK", "A.S.I.S. ready.")

    def _on_system_stopping(self, event: Event, state: AppState) -> None:
        state.shutdown_requested = True

    def _on_system_stopped(self, event: Event, state: AppState) -> None:
        pass

    def _on_system_failed(self, event: Event, state: AppState) -> None:
        msg = event.data.get("message", "Unknown system failure")
        state.add_boot_log("FAIL", msg)

    # --- Model handlers ---
    def _on_model_loading(self, event: Event, state: AppState) -> None:
        state.add_boot_log("BOOT", "Loading model...")
        state.model_ready = False

    def _on_model_loaded(self, event: Event, state: AppState) -> None:
        model = event.data.get("model", "unknown")
        state.model_name = model
        state.model_ready = True
        state.add_boot_log("OK", f"Model ready: {model}")

    def _on_model_unavailable(self, event: Event, state: AppState) -> None:
        state.model_ready = False
        msg = event.data.get("message", "Model unavailable")
        state.add_boot_log("FAIL", msg)

    # --- Inference handlers ---
    def _on_inference_started(self, event: Event, state: AppState) -> None:
        state.generating = True

    def _on_inference_finished(self, event: Event, state: AppState) -> None:
        state.generating = False

    def _on_inference_failed(self, event: Event, state: AppState) -> None:
        state.generating = False
        msg = event.data.get("message", "Inference failed")
        state.add_boot_log("FAIL", msg)

    def _on_inference_cancelled(self, event: Event, state: AppState) -> None:
        state.generating = False

    # --- Tool handlers ---
    def _on_tool_started(self, event: Event, state: AppState) -> None:
        tool_name = event.data.get("tool", "unknown")
        state.add_conversation_message(
            role="tool",
            content=f"[TOOL] {tool_name}",
            tool_name=tool_name,
            tool_status="STARTED"
        )

    def _on_tool_finished(self, event: Event, state: AppState) -> None:
        tool_name = event.data.get("tool", "unknown")
        result = event.data.get("result", "")
        state.set_tool_status(tool_name, "DONE")
        state.add_conversation_message(
            role="tool",
            content=f"[DONE] {tool_name}: {result}",
            tool_name=tool_name,
            tool_status="DONE"
        )

    def _on_tool_failed(self, event: Event, state: AppState) -> None:
        tool_name = event.data.get("tool", "unknown")
        error = event.data.get("error", "unknown error")
        state.set_tool_status(tool_name, "FAIL")
        state.add_conversation_message(
            role="tool",
            content=f"[FAIL] {tool_name}: {error}",
            tool_name=tool_name,
            tool_status="FAIL"
        )

    def _on_tool_denied(self, event: Event, state: AppState) -> None:
        tool_name = event.data.get("tool", "unknown")
        reason = event.data.get("reason", "permission denied")
        state.set_tool_status(tool_name, "FAIL")
        state.add_conversation_message(
            role="tool",
            content=f"[FAIL] {tool_name}: {reason}",
            tool_name=tool_name,
            tool_status="FAIL"
        )

    # --- Memory handlers ---
    def _on_memory_saved(self, event: Event, state: AppState) -> None:
        state.memory_ready = True
        state.add_conversation_message(
            role="system",
            content="[MEMORY] Context retrieved"
        )

    def _on_memory_deleted(self, event: Event, state: AppState) -> None:
        pass

    def _on_memory_cleared(self, event: Event, state: AppState) -> None:
        pass

    # --- Voice handlers ---
    def _on_voice_input(self, event: Event, state: AppState) -> None:
        state.voice_state = VoiceState.LISTENING

    def _on_voice_vad(self, event: Event, state: AppState) -> None:
        speech = event.data.get("speech", False)
        if speech and state.voice_state == VoiceState.LISTENING:
            state.voice_state = VoiceState.PROCESSING

    def _on_voice_stt_started(self, event: Event, state: AppState) -> None:
        state.voice_state = VoiceState.PROCESSING

    def _on_voice_stt_ready(self, event: Event, state: AppState) -> None:
        text = event.data.get("text", "")
        if text:
            state.add_conversation_message(
                role="user",
                content=text
            )
        state.voice_state = VoiceState.PROCESSING

    def _on_voice_speaker_identified(self, event: Event, state: AppState) -> None:
        speaker_id = event.data.get("speaker_id", "unknown")
        is_known = event.data.get("is_known", False)
        if is_known and speaker_id != "unknown":
            # Speaker identified, will be prepended to user message in stt_ready
            pass

    def _on_voice_wake_word(self, event: Event, state: AppState) -> None:
        phrases = event.data.get("phrases", [])
        state.add_boot_log("OK", f"Wake word detected: {phrases}")

    def _on_voice_assistant_started(self, event: Event, state: AppState) -> None:
        state.generating = True

    def _on_voice_assistant_finished(self, event: Event, state: AppState) -> None:
        state.generating = False
        response = event.data.get("response", "")
        if response:
            state.add_conversation_message(
                role="assistant",
                content=response
            )

    def _on_voice_tts_started(self, event: Event, state: AppState) -> None:
        state.voice_state = VoiceState.SPEAKING

    def _on_voice_tts_finished(self, event: Event, state: AppState) -> None:
        state.voice_state = VoiceState.READY

    def _on_voice_output(self, event: Event, state: AppState) -> None:
        pass

    def _on_voice_interrupted(self, event: Event, state: AppState) -> None:
        state.voice_state = VoiceState.READY
        state.generating = False

    def _on_voice_error(self, event: Event, state: AppState) -> None:
        state.voice_state = VoiceState.ERROR
        msg = event.data.get("message", "Voice error")
        state.add_boot_log("FAIL", f"Voice: {msg}")

    def _on_voice_stopped(self, event: Event, state: AppState) -> None:
        state.voice_state = VoiceState.OFF

    # --- Interrupt handlers ---
    def _on_interrupt_requested(self, event: Event, state: AppState) -> None:
        state.generating = False

    def _on_interrupt_cancelled(self, event: Event, state: AppState) -> None:
        pass

    # --- Error handler ---
    def _on_error_occurred(self, event: Event, state: AppState) -> None:
        msg = event.data.get("message", "Unknown error")
        state.add_boot_log("FAIL", msg)


def create_event_bridge(state: AppState, event_bus: EventBus | None = None) -> EventBridge:
    """Factory function to create and return an EventBridge."""
    return EventBridge(state, event_bus)
