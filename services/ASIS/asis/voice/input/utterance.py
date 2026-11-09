"""
Utterance capture for A.S.I.S. voice.

After wake-word activation, capture the user's command using VAD-gated
end-of-utterance detection:

    wake detected -> read chunks -> speech -> silence -> return segment

Bounded: never records indefinitely. Pure-python, no hardware required;
works with mocks in tests and real providers in production.
"""

from __future__ import annotations

from dataclasses import dataclass

from asis.errors import VoiceError
from asis.logging.logger import get_logger

from ..models import AudioData


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


@dataclass(frozen=True)
class UtteranceConfig:
    """Bounded end-of-utterance configuration."""

    sample_rate: int = 16_000
    channels: int = 1
    # Max total command audio in seconds (hard bound, prevents infinite record).
    max_utterance_seconds: float = 15.0
    # Silence after speech that ends the utterance.
    silence_seconds: float = 0.8
    # Max initial silence before giving up (returns what was captured).
    max_initial_silence_seconds: float = 5.0
    # Samples per read from the input provider.
    block_size: int = 1_024

    def __post_init__(self) -> None:
        if self.sample_rate <= 0 or self.channels <= 0 or self.block_size <= 0:
            raise ValueError("sample_rate/channels/block_size must be positive.")
        if self.max_utterance_seconds <= 0 or self.silence_seconds <= 0:
            raise ValueError("utterance/silence durations must be positive.")
        if self.max_initial_silence_seconds <= 0:
            raise ValueError("max_initial_silence_seconds must be positive.")


def _samples_per(values: list[float], sample_rate: int) -> float:
    return len(values) / float(sample_rate) if sample_rate > 0 else 0.0


def capture_utterance(
    audio_input,
    vad=None,
    seed: AudioData | None = None,
    config: UtteranceConfig | None = None,
    interrupts=None,
    scope: str = "voice",
) -> AudioData:
    """Capture one command utterance after wake-word activation.

    ``seed`` is the wake segment (included at the head so short commands
    spoken with the wake word are not lost). Reads additional chunks until
    VAD-observed silence, input exhaustion, or configured bounds. Returns
    canonical :class:`AudioData`. Never raises on silence — returns what
    was captured (possibly just the seed).
    """
    cfg = config or UtteranceConfig()
    logger = get_logger("voice.capture")

    def _check() -> None:
        if interrupts is not None:
            interrupts.check(scope)

    collected: list[float] = []
    sample_rate = cfg.sample_rate
    channels = cfg.channels
    if seed is not None:
        collected.extend(_to_float_list(seed.samples))
        sample_rate = seed.sample_rate or sample_rate
        channels = seed.channels or channels

    def _as_audio() -> AudioData:
        return AudioData(
            samples=list(collected),
            sample_rate=sample_rate,
            channels=channels,
            metadata={"captured": True},
        )

    # Without VAD we cannot detect end-of-speech: do a single bounded read
    # so behavior stays predictable with mocks.
    if vad is None:
        _check()
        try:
            chunk = audio_input.read(cfg.block_size)
        except Exception as exc:
            raise VoiceError(f"utterance capture failed: {exc}") from exc
        _check()
        extra = _to_float_list(chunk.samples)
        if extra:
            collected.extend(extra)
        # Enforce hard bound.
        max_samples = int(cfg.max_utterance_seconds * sample_rate)
        return AudioData(
            samples=collected[:max_samples],
            sample_rate=sample_rate,
            channels=channels,
            metadata={"captured": True},
        )

    max_samples = int(cfg.max_utterance_seconds * sample_rate)
    silence_needed = max(
        1, int(cfg.silence_seconds * sample_rate / cfg.block_size)
    )
    initial_limit = max(
        1, int(cfg.max_initial_silence_seconds * sample_rate / cfg.block_size)
    )

    silent_chunks = 0
    initial_silent = 0
    seen_speech = bool(collected) and _vad_says_speech(vad, collected, sample_rate)

    # Truncate seed to the hard bound immediately.
    if len(collected) > max_samples:
        collected = collected[:max_samples]
        return _as_audio()

    while len(collected) < max_samples:
        _check()
        try:
            chunk = audio_input.read(cfg.block_size)
        except Exception as exc:
            raise VoiceError(f"utterance capture failed: {exc}") from exc
        _check()
        extra = _to_float_list(chunk.samples)
        if not extra:
            # Input exhausted (mock) — stop.
            break
        # Keep within the hard bound.
        room = max_samples - len(collected)
        collected.extend(extra[:room])

        is_speech = _vad_says_speech(vad, extra, sample_rate)
        if is_speech:
            seen_speech = True
            silent_chunks = 0
            initial_silent = 0
        else:
            silent_chunks += 1
            if not seen_speech:
                initial_silent += 1
                if initial_silent >= initial_limit:
                    break
            elif silent_chunks >= silence_needed:
                break
        if len(collected) >= max_samples:
            break

    logger.info("utterance captured (%.2fs)", _samples_per(collected, sample_rate))
    return _as_audio()


def _vad_says_speech(vad, samples: list[float], sample_rate: int) -> bool:
    try:
        return bool(vad.is_speech(AudioData(samples=samples, sample_rate=sample_rate)))
    except Exception:
        return False
