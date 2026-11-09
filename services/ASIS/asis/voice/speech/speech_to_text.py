"""
Speech-to-text transcription (legacy helper, now canonical).

Uses Faster-Whisper with automatic language detection. Heavy imports
are lazy so base installs/tests never require them.
"""

from __future__ import annotations

from typing import Any

from ..models import TranscriptionResult

__all__ = ["TranscriptionResult", "SpeechTranscriber"]


def _to_float_samples(audio: Any) -> tuple[Any, int]:
    """Convert input to (flat float samples, size) without top-level numpy."""
    try:
        import numpy as np  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "numpy is required for STT. Install voice extras "
            "(`pip install -r requirements/voice.txt`)."
        ) from exc
    samples = np.asarray(audio, dtype=np.float32).flatten()
    return samples, int(samples.size)


class SpeechTranscriber:
    """Speech-to-text engine powered by Faster-Whisper."""

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str | None = None,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language or None

        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError as exc:
            from asis.errors import SpeechRecognitionError

            raise SpeechRecognitionError(
                "faster-whisper is not installed. Install voice extras "
                "(`pip install -r requirements/voice.txt`) or set "
                "ASIS_VOICE_STT_ENGINE=mock."
            ) from exc

        try:
            self.model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type,
            )
        except Exception as exc:
            from asis.errors import SpeechRecognitionError
            from asis.voice.model_cache import model_missing_message

            raise SpeechRecognitionError(
                model_missing_message(
                    engine="STT",
                    model=str(model_size),
                    setting="ASIS_VOICE_STT_ENGINE",
                    detail=str(exc)[:200],
                )
            ) from exc

    def transcribe(
        self,
        audio: Any,
        sample_rate: int = 16_000,
    ) -> TranscriptionResult:
        """
        Transcribe a speech segment.

        If language is None, Faster-Whisper automatically detects
        the spoken language.
        """
        try:
            samples, size = _to_float_samples(audio)
        except ImportError as exc:
            from asis.errors import SpeechRecognitionError

            raise SpeechRecognitionError(str(exc)) from exc

        if size == 0:
            return TranscriptionResult(
                text="",
                language=None,
                confidence=None,
                duration=0.0,
            )

        duration = size / float(sample_rate)

        try:
            segments, info = self.model.transcribe(
                samples,
                language=self.language,
                task="transcribe",
                beam_size=5,
                vad_filter=False,
            )
        except Exception as exc:
            from asis.errors import SpeechRecognitionError

            raise SpeechRecognitionError(f"transcription failed: {exc}") from exc

        text_parts: list[str] = []

        for segment in segments:
            text = segment.text.strip()

            if text:
                text_parts.append(text)

        text = " ".join(text_parts).strip()

        language = getattr(info, "language", None)
        language_probability = getattr(info, "language_probability", None)

        confidence: float | None = None
        if language_probability is not None:
            try:
                confidence = max(0.0, min(1.0, float(language_probability)))
            except (TypeError, ValueError):
                confidence = None

        return TranscriptionResult(
            text=text,
            language=language,
            confidence=confidence,
            duration=duration,
        )
