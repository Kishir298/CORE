"""
Real cross-platform audio output via sounddevice.
"""

from __future__ import annotations

from asis.errors import VoiceError
from asis.logging.logger import get_logger

from ..models import AudioData
from ..providers import AudioOutputProvider


def _to_float_list(samples: object) -> list[float]:
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


class SoundDeviceOutputProvider(AudioOutputProvider):
    """Play :class:`AudioData` through the default output device."""

    def __init__(
        self,
        sample_rate: int = 16_000,
        channels: int = 1,
        device: int | str | None = None,
    ) -> None:
        if sample_rate <= 0 or channels <= 0:
            raise ValueError("sample_rate/channels must be positive.")
        self._sample_rate = sample_rate
        self._channels = channels
        self._device = device
        self._playing = False
        self._logger = get_logger("voice.output.sounddevice")

    def play(self, audio: AudioData) -> None:
        if not isinstance(audio, AudioData):
            raise VoiceError("audio must be AudioData.")
        if audio.sample_rate <= 0 or audio.channels <= 0:
            raise VoiceError("invalid audio sample rate/channels.")
        samples = _to_float_list(audio.samples)
        if not samples:
            raise VoiceError("no audio samples to play.")
        try:
            import sounddevice as sd  # type: ignore
        except ImportError as exc:
            raise VoiceError(
                "sounddevice is not installed. Install voice extras "
                "(`pip install -r requirements/voice.txt`) or set "
                "ASIS_VOICE_OUTPUT_ENGINE=mock."
            ) from exc
        try:
            import numpy as np  # type: ignore

            arr = np.asarray(samples, dtype=np.float32)
            if audio.channels != self._channels:
                self._logger.warning(
                    "channel mismatch: audio=%d expected=%d",
                    audio.channels,
                    self._channels,
                )
            sd.play(arr, samplerate=audio.sample_rate, device=self._device)
            self._playing = True
        except Exception as exc:
            raise VoiceError(f"audio playback failed: {exc}") from exc

    def stop(self) -> None:
        try:
            import sounddevice as sd  # type: ignore
        except ImportError:
            self._playing = False
            return
        try:
            sd.stop()
        except Exception as exc:
            raise VoiceError(f"could not stop playback: {exc}") from exc
        finally:
            self._playing = False
