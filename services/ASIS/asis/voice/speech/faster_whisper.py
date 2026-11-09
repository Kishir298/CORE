"""
Local Faster-Whisper STT provider behind :class:`SpeechRecognizer`.

Configuration-driven (model/device/compute_type/language); all heavy
imports are lazy so ``pytest`` without voice extras still works.
"""

from __future__ import annotations

from asis.errors import SpeechRecognitionError
from asis.logging.logger import get_logger

from ..models import AudioData, TranscriptionResult
from ..providers import SpeechRecognizer
from .speech_to_text import SpeechTranscriber


class FasterWhisperRecognizer(SpeechRecognizer):
    """Real local STT: ``AudioData`` -> canonical ``TranscriptionResult``."""

    def __init__(
        self,
        model: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str | None = None,
    ) -> None:
        self._model_name = model
        self._device = device
        self._compute_type = compute_type
        self._language = language or None
        self._logger = get_logger("voice.stt.faster_whisper")
        try:
            self._engine = SpeechTranscriber(
                model_size=model,
                device=device,
                compute_type=compute_type,
                language=self._language,
            )
        except SpeechRecognitionError:
            raise
        except ImportError as exc:
            raise SpeechRecognitionError(str(exc)) from exc

    @property
    def model_name(self) -> str:
        return self._model_name

    def transcribe(self, audio: AudioData) -> TranscriptionResult:
        if not isinstance(audio, AudioData):
            raise SpeechRecognitionError("audio must be AudioData.")
        if audio.sample_rate <= 0:
            raise SpeechRecognitionError("invalid sample rate.")
        try:
            result = self._engine.transcribe(
                audio.samples, sample_rate=audio.sample_rate
            )
        except SpeechRecognitionError:
            raise
        except Exception as exc:
            raise SpeechRecognitionError(f"transcription failed: {exc}") from exc
        self._logger.debug("transcribed %d chars", len(result.text))
        return result
