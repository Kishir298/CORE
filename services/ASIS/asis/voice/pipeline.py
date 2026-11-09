"""
Voice pipeline for A.S.I.S.

Coordinates replaceable providers: capture -> VAD -> wake word ->
transcribe -> identify speaker -> synthesize -> output. Emits voice
events and honors the ``voice`` interruption scope so active speech
can be cancelled. Depends on interfaces only, never on concrete
Whisper/openWakeWord/TTS/sounddevice implementations.
"""

from __future__ import annotations

from collections.abc import Callable

from asis.errors import CancellationError, VoiceError
from asis.events.bus import EventBus
from asis.events.events import EventType
from asis.logging.logger import get_logger
from asis.system.interrupt import InterruptCoordinator

from .models import AudioData, SpeakerResult, TranscriptionResult, VoiceEvent
from .providers import (
    AudioInputProvider,
    AudioOutputProvider,
    SpeakerIdentifier,
    SpeechRecognizer,
    TextToSpeechProvider,
    VadDetector,
    WakeWordDetector,
)

_VOICE_SCOPE = "voice"


class VoicePipeline:
    """Coordinate replaceable voice providers."""

    def __init__(
        self,
        audio_input: AudioInputProvider,
        speech_recognizer: SpeechRecognizer,
        speaker_identifier: SpeakerIdentifier,
        tts: TextToSpeechProvider,
        audio_output: AudioOutputProvider,
        event_bus: EventBus | None = None,
        interrupts: InterruptCoordinator | None = None,
        vad: VadDetector | None = None,
        wake_word_detector: WakeWordDetector | None = None,
        normalizer=None,
        utterance_capturer: Callable[[AudioData], AudioData] | None = None,
    ) -> None:
        self.audio_input = audio_input
        self.speech_recognizer = speech_recognizer
        self.speaker_identifier = speaker_identifier
        self.tts = tts
        self.audio_output = audio_output
        self.event_bus = event_bus
        self.interrupts = interrupts
        self.vad = vad
        self.wake_word_detector = wake_word_detector
        self.normalizer = normalizer
        self.utterance_capturer = utterance_capturer
        self._logger = get_logger("voice.pipeline")

    # -- internals -----------------------------------------------------
    def _check(self) -> None:
        if self.interrupts is not None:
            self.interrupts.check(_VOICE_SCOPE)

    def _publish(
        self,
        event_type: EventType,
        **data,
    ) -> None:
        if self.event_bus is None:
            return
        event = VoiceEvent(event_type=event_type, payload=dict(data)).to_event()
        self.event_bus.publish(event)

    def _fail(self, message: str, exc: Exception | None = None) -> VoiceError:
        self._publish(EventType.VOICE_ERROR, message=message)
        self._logger.error("voice error: %s", message)
        if isinstance(exc, VoiceError):
            return exc
        return VoiceError(message) if exc is None else VoiceError(f"{message}: {exc}")

    # -- stages (each independently testable) --------------------------
    def listen(self, num_samples: int = 1024) -> AudioData:
        """Capture one audio segment (cancellable)."""
        self._check()
        try:
            audio = self.audio_input.read(num_samples)
        except Exception as exc:
            raise self._fail("audio capture failed", exc) from exc
        self._publish(EventType.VOICE_INPUT)
        self._check()
        return audio

    def check_voice_activity(self, audio: AudioData) -> bool:
        """Return True when audio likely contains speech (VAD gate)."""
        if self.vad is None:
            return True
        try:
            speech = bool(self.vad.is_speech(audio))
        except Exception as exc:
            raise self._fail("VAD failed", exc) from exc
        self._publish(EventType.VOICE_VAD, speech=speech)
        return speech

    def capture_command(self, audio: AudioData) -> AudioData:
        """Capture the full command utterance after wake-word activation.

        Defaults to the wake segment itself; when ``utterance_capturer``
        is set (real VAD-gated capture), use it bounded and fail-open to
        the seed segment on error.
        """
        if self.utterance_capturer is None:
            return audio
        self._check()
        try:
            captured = self.utterance_capturer(audio)
        except Exception as exc:
            self._logger.warning("utterance capture failed, using seed: %s", exc)
            return audio
        self._check()
        if captured is None:
            return audio
        return captured

    def detect_wake_word(self, audio: AudioData) -> bool:
        """Audio wake-word check; publishes event when detected."""
        if self.wake_word_detector is None:
            return True
        try:
            detected = bool(self.wake_word_detector.detect(audio))
        except Exception as exc:
            raise self._fail("wake-word detection failed", exc) from exc
        if detected:
            self._publish(
                EventType.VOICE_WAKE_WORD_DETECTED,
                phrases=list(self.wake_word_detector.phrases),
            )
            self._logger.info("wake word detected")
        return detected

    def detect_wake_text(self, text: str) -> bool:
        """Text-surface wake check via the detector fallback."""
        if self.wake_word_detector is None:
            return True
        try:
            detected = bool(self.wake_word_detector.detect_text(text))
        except Exception:
            return False
        if detected:
            self._publish(EventType.VOICE_WAKE_WORD_DETECTED, text=text[:120])
        return detected

    def transcribe(self, audio: AudioData) -> TranscriptionResult:
        """Convert audio into text (cancellable around inference)."""
        self._check()
        self._publish(EventType.VOICE_STT_STARTED)

        try:
            result = self.speech_recognizer.transcribe(audio)
        except Exception as exc:
            raise self._fail("speech recognition failed", exc) from exc

        self._check()
        self._publish(
            EventType.VOICE_STT_READY,
            text=result.text,
            language=result.language,
        )
        self._logger.info("STT ready (%d chars)", len(result.text))
        return result

    def identify_speaker(self, audio: AudioData) -> SpeakerResult:
        """Identify the speaker of the audio (cancellable)."""
        self._check()
        try:
            result = self.speaker_identifier.identify(audio)
        except Exception as exc:
            raise self._fail("speaker identification failed", exc) from exc

        self._check()
        self._publish(
            EventType.VOICE_SPEAKER_IDENTIFIED,
            speaker_id=result.speaker_id,
            is_known=result.is_known,
        )
        return result

    def normalize_text(self, text: str) -> str:
        """Optionally normalize STT output; passthrough when unset."""
        if self.normalizer is None:
            return text
        try:
            result = self.normalizer.normalize(text)
            return result.normalized_text
        except Exception as exc:
            self._logger.warning("normalization failed: %s", exc)
            return text

    def speak(self, text: str) -> AudioData:
        """Synthesize and output speech (cancellable)."""
        self._check()
        self._publish(EventType.VOICE_TTS_STARTED, text=text[:200])

        try:
            audio = self.tts.synthesize(text)
        except Exception as exc:
            raise self._fail("TTS synthesis failed", exc) from exc

        self._check()

        try:
            self.audio_output.play(audio)
        except Exception as exc:
            raise self._fail("audio output failed", exc) from exc

        self._check()
        self._publish(EventType.VOICE_TTS_FINISHED)
        self._publish(EventType.VOICE_OUTPUT)
        self._logger.info("TTS finished (%d chars)", len(text))
        return audio

    # -- legacy helpers ------------------------------------------------
    def _expects_input(self) -> AudioData:
        return self.listen(1024)

    def listen_and_transcribe(self) -> TranscriptionResult:
        """Capture a segment and transcribe it."""
        audio = self._expects_input()
        return self.transcribe(audio)

    # -- full orchestration --------------------------------------------
    def run_once(
        self,
        process_fn: Callable[[str, SpeakerResult], str] | None = None,
        require_wake_word: bool = False,
        num_samples: int = 1024,
    ) -> dict:
        """Run input->VAD->wake(audio)->capture->STT->speaker->A.S.I.S.->TTS.

        Audio-level wake gating avoids transcribing ambient speech: when
        ``require_wake_word`` is set, ``detect_wake_word(audio)`` runs
        before STT and a miss returns ``no-wake-word`` without inference.
        A text-level ``detect_wake_text`` confirmation still applies after
        STT for phrase accuracy (mock/keyphrase fallback).

        Returns ``{text, speaker, response, status}`` with status
        ``spoken`` | ``no-speech`` | ``no-wake-word``.
        """
        try:
            audio = self.listen(num_samples)

            if not self.check_voice_activity(audio):
                return {
                    "status": "no-speech",
                    "text": "",
                    "speaker": None,
                    "response": "",
                }

            if require_wake_word and not self.detect_wake_word(audio):
                # Audio gate miss: skip expensive STT entirely.
                return {
                    "status": "no-wake-word",
                    "text": "",
                    "speaker": None,
                    "response": "",
                }

            if require_wake_word:
                audio = self.capture_command(audio)

            result = self.transcribe(audio)
            text = self.normalize_text(result.text)

            if require_wake_word and not self.detect_wake_text(text):
                return {
                    "status": "no-wake-word",
                    "text": text,
                    "speaker": None,
                    "response": "",
                }

            speaker = self.identify_speaker(audio)

            if process_fn is None:
                response = text
            else:
                self._check()
                self._publish(EventType.VOICE_ASSISTANT_STARTED, text=text[:200])
                response = ""
                try:
                    response = process_fn(text, speaker)
                finally:
                    self._publish(
                        EventType.VOICE_ASSISTANT_FINISHED,
                        response=(response or "")[:200],
                    )
                self._check()

            if not response or not response.strip():
                return {
                    "status": "spoken",
                    "text": text,
                    "speaker": speaker,
                    "response": "",
                }

            self.speak(response)
            return {
                "status": "spoken",
                "text": text,
                "speaker": speaker,
                "response": response,
            }
        except CancellationError:
            self._publish(EventType.VOICE_INTERRUPTED)
            raise

    def stop(self) -> None:
        """Stop active voice operations and release audio resources."""
        try:
            self.audio_input.stop()
        finally:
            try:
                self.audio_output.stop()
            finally:
                self._publish(EventType.VOICE_STOPPED)
                self._logger.info("voice pipeline stopped")
