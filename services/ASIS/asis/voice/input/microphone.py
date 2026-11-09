"""
Microphone input interface.

Cross-platform microphone discovery and audio capture. Heavy imports
are lazy so base installs/tests never require them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MicrophoneConfig:
    """Configuration for microphone capture."""

    sample_rate: int = 16_000
    channels: int = 1
    block_size: int = 1_024
    dtype: str = "float32"
    device: int | None = None


def _require_sounddevice() -> Any:
    try:
        import sounddevice as sd  # type: ignore
    except ImportError as exc:
        from asis.errors import VoiceError

        raise VoiceError(
            "sounddevice is not installed. Install voice extras "
            "(`pip install -r requirements/voice.txt`) or set "
            "ASIS_VOICE_INPUT_ENGINE=mock."
        ) from exc
    return sd


class Microphone:
    """Cross-platform microphone interface."""

    def __init__(
        self,
        config: MicrophoneConfig | None = None,
    ) -> None:
        self.config = config or MicrophoneConfig()
        self._stream: Any = None

    @staticmethod
    def list_devices() -> list[dict]:
        """Return available input devices."""

        sd = _require_sounddevice()
        devices = sd.query_devices()

        return [
            {
                "index": index,
                "name": device["name"],
                "input_channels": device["max_input_channels"],
                "sample_rate": device["default_samplerate"],
            }
            for index, device in enumerate(devices)
            if device["max_input_channels"] > 0
        ]

    @property
    def is_running(self) -> bool:
        """Return whether the microphone stream is active."""

        return self._stream is not None and bool(self._stream.active)

    def start(self) -> None:
        """Start microphone capture."""

        if self.is_running:
            return

        sd = _require_sounddevice()
        self._stream = sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            blocksize=self.config.block_size,
            dtype=self.config.dtype,
            device=self.config.device,
        )

        self._stream.start()

    def read(self, frames: int | None = None) -> Any:
        """
        Read audio frames.

        Returns a NumPy array when numpy/sounddevice are available.
        Raises RuntimeError when not running, VoiceError when deps miss.
        """

        if not self.is_running:
            raise RuntimeError("Microphone is not running.")

        frame_count = frames or self.config.block_size

        audio, _overflowed = self._stream.read(frame_count)

        try:
            import numpy as np  # type: ignore

            return np.asarray(audio, dtype=np.float32)
        except ImportError:
            return audio

    def stop(self) -> None:
        """Stop microphone capture and release resources."""

        if self._stream is None:
            return

        try:
            self._stream.stop()
        finally:
            try:
                self._stream.close()
            finally:
                self._stream = None

    def __enter__(self) -> Microphone:
        self.start()
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.stop()
