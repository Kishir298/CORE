"""
Local audio wake-word provider using openWakeWord (optional).

Lazy imports so base installs/tests never require the heavy dep.
Text-surface ``KeyphraseWakeWordDetector`` remains the lightweight
fallback and is preserved untouched.
"""

from __future__ import annotations

from collections.abc import Iterable

from asis.errors import VoiceError
from asis.logging.logger import get_logger

from ..models import AudioData
from ..providers import WakeWordDetector


def _to_float_samples(samples: object) -> list[float]:
    if samples is None:
        return []
    try:
        import numpy as np  # type: ignore

        if isinstance(samples, np.ndarray):
            return [float(v) for v in samples.flatten().tolist()]
    except ImportError:
        pass
    if isinstance(samples, (list, tuple)):
        out: list[float] = []
        for item in samples:
            if isinstance(item, (list, tuple)):
                out.extend(float(v) for v in item)
            else:
                try:
                    out.append(float(item))  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    continue
        return out
    return []


class OpenWakeWordDetector(WakeWordDetector):
    """Audio wake-word detection via openWakeWord (local, no cloud)."""

    def __init__(
        self,
        phrases: Iterable[str] = ("hey asis",),
        threshold: float = 0.5,
        model_path: str | None = None,
    ) -> None:
        cleaned = {p.strip().casefold() for p in phrases if p.strip()}
        if not cleaned:
            raise ValueError("at least one wake phrase is required.")
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be between 0.0 and 1.0.")
        self._phrases = tuple(cleaned)
        self._threshold = threshold
        self._model_path = model_path or None
        self._logger = get_logger("voice.wakeword.openwakeword")
        try:
            from openwakeword.model import Model  # type: ignore
        except ImportError as exc:
            raise VoiceError(
                "openwakeword is not installed. Install voice extras "
                "(`pip install -r requirements/voice.txt`) or set "
                "ASIS_VOICE_WAKE_ENGINE=mock."
            ) from exc
        try:
            if self._model_path:
                self._model = Model(
                    wakeword_models=[self._model_path],
                    inference_framework="onnx",
                )
            else:
                self._model = Model(inference_framework="onnx")
        except Exception as exc:
            from asis.voice.model_cache import model_missing_message

            raise VoiceError(
                model_missing_message(
                    engine="wake-word",
                    model=str(self._model_path)
                    if self._model_path
                    else "openwakeword-default",
                    setting="ASIS_VOICE_WAKE_ENGINE",
                    detail=str(exc)[:200],
                )
            ) from exc

    @property
    def phrases(self) -> tuple[str, ...]:
        return self._phrases

    @property
    def threshold(self) -> float:
        return self._threshold

    def detect(self, audio: AudioData) -> bool:
        samples = _to_float_samples(audio.samples)
        if not samples:
            return False
        try:
            import numpy as np  # type: ignore

            arr = np.asarray(samples, dtype=np.float32)
            scores = self._model.predict(arr)
        except ImportError as exc:
            raise VoiceError(
                "numpy is required for wake-word detection. Install voice extras."
            ) from exc
        except Exception as exc:
            raise VoiceError(f"wake-word inference failed: {exc}") from exc
        try:
            for _model_name, score in scores.items():
                value = float(score[-1] if hasattr(score, "__len__") else score)
                if value >= self._threshold:
                    self._logger.debug("wake word detected (%.3f)", value)
                    return True
        except Exception:
            return False
        return False
