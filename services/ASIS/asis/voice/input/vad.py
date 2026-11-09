"""
Voice Activity Detection (lazy Silero VAD + provider adapter).

Top-level imports stay light so base installs/tests never require
torch/silero. Real inference happens only when constructed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from asis.errors import VoiceError

from ..models import AudioData
from ..providers import VadDetector


def _to_float_list(samples: Any) -> list[float]:
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


class VoiceActivityDetector:
    """Detect human speech using Silero VAD (legacy concrete class)."""

    SUPPORTED_SAMPLE_RATES = {8_000, 16_000}

    FRAME_SIZES = {
        8_000: 256,
        16_000: 512,
    }

    def __init__(
        self,
        sample_rate: int = 16_000,
        threshold: float = 0.5,
        model_path: str | Path | None = None,
    ) -> None:
        if sample_rate not in self.SUPPORTED_SAMPLE_RATES:
            raise ValueError(
                f"Unsupported sample rate: {sample_rate}. Use 8000 or 16000 Hz."
            )

        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be between 0.0 and 1.0.")

        self.sample_rate = sample_rate
        self.threshold = threshold
        self.frame_size = self.FRAME_SIZES[sample_rate]

        try:
            import torch  # type: ignore
            from silero_vad import load_silero_vad  # type: ignore
        except ImportError as exc:
            raise VoiceError(
                "silero-vad/torch is not installed. Install voice extras "
                "(`pip install -r requirements/voice.txt`) or set "
                "ASIS_VOICE_VAD_ENGINE=mock."
            ) from exc

        self.device = torch.device("cpu")

        try:
            if model_path is not None:
                self.model = load_silero_vad(model_path=str(model_path))
            else:
                self.model = load_silero_vad()
        except Exception as exc:
            from asis.voice.model_cache import model_missing_message

            raise VoiceError(
                model_missing_message(
                    engine="VAD",
                    model=str(model_path) if model_path is not None else "silero-vad",
                    setting="ASIS_VOICE_VAD_ENGINE",
                    detail=str(exc)[:200],
                )
            ) from exc

        self.model.to(self.device)
        self.model.eval()

    def speech_probability(self, audio: Any) -> float:
        """Return the highest speech probability found in the audio."""

        try:
            import numpy as np  # type: ignore
            import torch  # type: ignore
        except ImportError as exc:
            raise VoiceError("torch/numpy required for VAD.") from exc

        if isinstance(audio, AudioData):
            flat = _to_float_list(audio.samples)
            samples = np.asarray(flat, dtype=np.float32)
        else:
            samples = np.asarray(audio, dtype=np.float32).flatten()
            samples = np.clip(samples, -1.0, 1.0)

        if samples.size == 0:
            return 0.0

        probabilities: list[float] = []

        for start in range(0, samples.size, self.frame_size):
            frame = samples[start : start + self.frame_size]

            if frame.size < self.frame_size:
                break

            tensor = torch.from_numpy(frame).to(self.device)

            with torch.no_grad():
                probability = self.model(tensor, self.sample_rate).item()

            probabilities.append(float(probability))

        if not probabilities:
            return 0.0

        return max(probabilities)

    def is_speech(self, audio: Any) -> bool:
        """Determine whether speech exists in the supplied audio."""

        return self.speech_probability(audio) >= self.threshold

    def reset(self) -> None:
        """Reset the VAD model's internal state."""

        if hasattr(self.model, "reset_states"):
            self.model.reset_states()


class SileroVadDetector(VadDetector):
    """Adapter exposing Silero VAD behind the :class:`VadDetector` ABC."""

    def __init__(self, sample_rate: int = 16_000, threshold: float = 0.5) -> None:
        self._vad = VoiceActivityDetector(sample_rate=sample_rate, threshold=threshold)

    def is_speech(self, audio: AudioData) -> bool:
        try:
            return bool(self._vad.is_speech(audio))
        except VoiceError:
            raise
        except Exception as exc:
            raise VoiceError(f"VAD failed: {exc}") from exc
