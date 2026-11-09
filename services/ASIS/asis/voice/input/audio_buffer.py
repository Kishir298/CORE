"""
Audio buffering.

Thread-safe buffer for microphone audio. Works without numpy (pure
python lists); uses numpy when available for concatenation.
"""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Any


def _flatten(samples: Any) -> list[float]:
    if samples is None:
        return []
    try:
        import numpy as np  # type: ignore

        if isinstance(samples, np.ndarray):
            return [float(v) for v in samples.flatten().tolist()]
    except ImportError:
        pass
    if isinstance(samples, (bytes, bytearray)):
        return [float(b) for b in samples]
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
    try:
        return [float(samples)]  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return []


class AudioBuffer:
    """Thread-safe audio sample buffer."""

    def __init__(
        self,
        max_seconds: float = 30.0,
        sample_rate: int = 16_000,
    ) -> None:
        if max_seconds <= 0:
            raise ValueError("max_seconds must be greater than zero.")

        if sample_rate <= 0:
            raise ValueError("sample_rate must be greater than zero.")

        self.sample_rate = sample_rate
        self.max_samples = int(max_seconds * sample_rate)

        self._buffer: deque[list[float]] = deque()
        self._sample_count = 0
        self._lock = Lock()

    @property
    def sample_count(self) -> int:
        """Return the number of samples currently buffered."""

        with self._lock:
            return self._sample_count

    @property
    def duration_seconds(self) -> float:
        """Return the buffered audio duration in seconds."""

        return self.sample_count / self.sample_rate

    def write(self, audio: Any) -> None:
        """Add audio samples to the buffer."""

        samples = _flatten(audio)

        if not samples:
            return

        with self._lock:
            self._buffer.append(samples)
            self._sample_count += len(samples)

            while self._sample_count > self.max_samples:
                oldest = self._buffer.popleft()
                self._sample_count -= len(oldest)

    def _concat(self) -> list[float]:
        with self._lock:
            if not self._buffer:
                return []
            return [v for chunk in self._buffer for v in chunk]

    def read(self, seconds: float | None = None) -> list[float]:
        """Read buffered audio without removing it."""

        audio = self._concat()

        if not audio:
            return []

        if seconds is None:
            return list(audio)

        if seconds <= 0:
            raise ValueError("seconds must be greater than zero.")

        sample_count = min(int(seconds * self.sample_rate), len(audio))

        return audio[-sample_count:]

    def consume(self, seconds: float | None = None) -> list[float]:
        """Read and remove audio from the buffer."""

        with self._lock:
            if not self._buffer:
                return []

            audio = [v for chunk in self._buffer for v in chunk]

            if seconds is None:
                self._buffer.clear()
                self._sample_count = 0
                return audio

            if seconds <= 0:
                raise ValueError("seconds must be greater than zero.")

            sample_count = min(int(seconds * self.sample_rate), len(audio))

            result = audio[-sample_count:]
            remaining = audio[:-sample_count]

            self._buffer.clear()
            self._sample_count = 0

            if remaining:
                self._buffer.append(remaining)
                self._sample_count = len(remaining)

            return result

    def clear(self) -> None:
        """Remove all buffered audio."""

        with self._lock:
            self._buffer.clear()
            self._sample_count = 0
