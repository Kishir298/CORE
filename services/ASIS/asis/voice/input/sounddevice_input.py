"""
SoundDevice audio input adapter behind :class:`AudioInputProvider`.
"""

from __future__ import annotations

from asis.errors import VoiceError
from asis.logging.logger import get_logger

from ..models import AudioData
from ..providers import AudioInputProvider
from .microphone import Microphone, MicrophoneConfig


class SoundDeviceInputProvider(AudioInputProvider):
    """Real microphone capture returning canonical :class:`AudioData`."""

    def __init__(
        self,
        sample_rate: int = 16_000,
        channels: int = 1,
        block_size: int = 1_024,
        device: int | None = None,
    ) -> None:
        if sample_rate <= 0 or channels <= 0 or block_size <= 0:
            raise ValueError("sample_rate/channels/block_size must be positive.")
        self._config = MicrophoneConfig(
            sample_rate=sample_rate,
            channels=channels,
            block_size=block_size,
            device=device,
        )
        self._mic = Microphone(self._config)
        self._logger = get_logger("voice.input.sounddevice")

    def start(self) -> None:
        try:
            self._mic.start()
        except VoiceError:
            raise
        except Exception as exc:
            raise VoiceError(f"could not start microphone: {exc}") from exc
        self._logger.info(
            "microphone started (%dHz, %dch)",
            self._config.sample_rate,
            self._config.channels,
        )

    def read(self, num_samples: int) -> AudioData:
        if num_samples <= 0:
            raise VoiceError("num_samples must be positive.")
        try:
            raw = self._mic.read(num_samples)
        except RuntimeError:
            raise
        except VoiceError:
            raise
        except Exception as exc:
            raise VoiceError(f"microphone read failed: {exc}") from exc
        try:
            import numpy as np  # type: ignore

            if isinstance(raw, np.ndarray):
                samples: object = raw.flatten().tolist()
            else:
                samples = raw
        except ImportError:
            samples = raw
        return AudioData(
            samples=samples,
            sample_rate=self._config.sample_rate,
            channels=self._config.channels,
        )

    def stop(self) -> None:
        try:
            self._mic.stop()
        except Exception as exc:
            raise VoiceError(f"could not stop microphone: {exc}") from exc
