"""
Controlled voice listening loop for A.S.I.S.

``VoiceRunner`` owns the waiting -> wake -> command -> response -> waiting
cycle without spinning at 100% CPU, leaking streams, or re-initializing
models. One pipeline (one set of providers) is reused across turns.
Implements :class:`RuntimeComponent` so ``ASISRuntime`` shutdown timeout
and lifecycle ordering apply.
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from asis.errors import ASISError, CancellationError
from asis.logging.logger import get_logger
from asis.system.component import RuntimeComponent

from .commands import parse_voice_mode_command
from .models import SpeakerResult
from .pipeline import VoicePipeline


@dataclass(frozen=True)
class VoiceRunnerConfig:
    """Bounded loop configuration."""

    require_wake_word: bool = True
    max_turns: int = 0  # 0 = infinite until stop/shutdown-phrase
    shutdown_phrase: str = "asis shutdown"
    idle_sleep_seconds: float = 0.05
    num_samples: int = 1_024

    def __post_init__(self) -> None:
        if self.max_turns < 0:
            raise ValueError("max_turns must be >= 0.")
        if self.idle_sleep_seconds < 0:
            raise ValueError("idle_sleep_seconds must be >= 0.")
        if self.num_samples <= 0:
            raise ValueError("num_samples must be positive.")


class VoiceRunner(RuntimeComponent):
    """Reusable, cancellable voice loop around one pipeline + AssistantApp."""

    name = "voice"

    def __init__(
        self,
        pipeline: VoicePipeline,
        app=None,
        config: VoiceRunnerConfig | None = None,
        on_response: Callable[[str, dict], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.app = app
        self.config = config or VoiceRunnerConfig()
        self.on_response = on_response
        self.on_error = on_error
        self._stop_event = threading.Event()
        self._turns = 0
        self._logger = get_logger("voice.runner")

    @property
    def turns(self) -> int:
        return self._turns

    @property
    def stopped(self) -> bool:
        return self._stop_event.is_set()

    def request_stop(self) -> None:
        """Signal the loop to exit after the current turn."""
        self._stop_event.set()
        interrupts = getattr(self.pipeline, "interrupts", None)
        if interrupts is not None:
            with contextlib.suppress(Exception):
                interrupts.cancel("voice")

    # -- RuntimeComponent ------------------------------------------------
    def start(self, context) -> None:  # type: ignore[no-untyped-def]
        self._stop_event.clear()
        try:
            self.pipeline.audio_input.start()
        except Exception as exc:
            raise ASISError(f"voice startup failed: {exc}") from exc
        self._logger.info("voice runner started")

    def stop(self, context) -> None:  # type: ignore[no-untyped-def]
        self._stop_event.set()
        interrupts = getattr(self.pipeline, "interrupts", None)
        if interrupts is not None:
            with contextlib.suppress(Exception):
                interrupts.cancel("voice")
        try:
            self.pipeline.stop()
        except Exception as exc:
            self._logger.warning("voice stop warning: %s", exc)
        self._logger.info("voice runner stopped")

    # -- per-turn processing ---------------------------------------------
    def _process(self, text: str, speaker: SpeakerResult | None) -> str:
        """Route transcript through mode commands or AssistantApp."""
        mode = parse_voice_mode_command(text)
        if mode is not None and self.app is not None:
            self.app.set_mode(mode)
            if mode.value == "coding":
                try:
                    root = self.app.workspace.root
                except Exception:
                    root = ""
                return f"A.S.C.S. coding mode enabled.\nWorkspace: {root}".strip()
            return "A.S.I.S. general mode enabled."
        if self.app is not None:
            # Speaker-aware prefix for memory/tools; no separate voice memory.
            known = (
                speaker is not None
                and speaker.is_known
                and speaker.speaker_id != "unknown"
            )
            if known and speaker is not None:
                return self.app.chat(f"[{speaker.speaker_id}] {text}")
            return self.app.chat(text)
        return text

    def run_once_turn(self) -> dict:
        """Run a single turn through the shared pipeline."""
        return self.pipeline.run_once(
            process_fn=self._process,
            require_wake_word=self.config.require_wake_word,
            num_samples=self.config.num_samples,
        )

    def _is_mock_exhausted(self) -> bool:
        audio_input = getattr(self.pipeline, "audio_input", None)
        segments = getattr(audio_input, "_segments", None)
        index = getattr(audio_input, "_index", None)
        return (
            isinstance(segments, list)
            and isinstance(index, int)
            and index >= len(segments)
        )

    def run(self) -> dict[str, Any]:
        """Loop until stop/shutdown-phrase/max-turns. Returns summary."""
        shutdown = (self.config.shutdown_phrase or "").strip().casefold()
        max_turns = self.config.max_turns
        turns = 0
        reason = "stopped"
        try:
            while not self._stop_event.is_set():
                if max_turns and turns >= max_turns:
                    reason = "max-turns"
                    break
                try:
                    result = self.run_once_turn()
                except CancellationError:
                    reason = "cancelled"
                    break
                except ASISError as exc:
                    if self.on_error is not None:
                        with contextlib.suppress(Exception):
                            self.on_error(exc)
                    self._logger.warning("voice turn error: %s", exc)
                    continue

                status = result.get("status")
                text = (result.get("text") or "").strip()
                if not text and status in {"no-speech", "no-wake-word"}:
                    if self._is_mock_exhausted():
                        reason = "input-exhausted"
                        break
                    if self.config.idle_sleep_seconds:
                        time.sleep(self.config.idle_sleep_seconds)
                    continue
                if shutdown and text.casefold() == shutdown:
                    reason = "shutdown-phrase"
                    with contextlib.suppress(Exception):
                        self.pipeline.speak("Shutting down.")
                    break
                if result.get("response") and self.on_response is not None:
                    with contextlib.suppress(Exception):
                        self.on_response(result["response"], result)
                turns += 1
                self._turns = turns
        except KeyboardInterrupt:
            reason = "keyboard-interrupt"
        return {"turns": turns, "reason": reason}
