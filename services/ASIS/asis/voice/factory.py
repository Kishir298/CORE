"""
Voice component factory for A.S.I.S.

Builds the configured set of voice engines. When a selected engine is
unavailable (missing hardware or optional dependencies), a helpful
error is raised instead of silently failing. Never reads env directly;
uses centralized ``settings``.
"""

from __future__ import annotations

from pathlib import Path

from asis.configuration.settings import settings
from asis.errors import VoiceError
from asis.logging.logger import get_logger

from .engines.mock import (
    MockAudioInput,
    MockAudioOutput,
    MockSpeakerEmbeddingProvider,
    MockSpeakerIdentifier,
    MockSpeechRecognizer,
    MockTextToSpeech,
    MockVadDetector,
    MockWakeWordDetector,
)
from .models import AudioData
from .providers import (
    AudioInputProvider,
    AudioOutputProvider,
    SpeakerEmbeddingProvider,
    SpeakerIdentifier,
    SpeechRecognizer,
    TextToSpeechProvider,
    VadDetector,
    WakeWordDetector,
)


def _unsupported(engine: str, kind: str):
    return VoiceError(
        f"The '{engine}' {kind} engine is not provided yet. "
        f"Install the voice extras and implement the provider, or "
        f"set ASIS_VOICE_{kind.upper()}_ENGINE=mock."
    )


def create_speech_recognizer() -> SpeechRecognizer:
    """Build the configured speech recognition engine."""
    engine = (settings.voice.stt.engine or "mock").lower()

    if engine in {"mock", ""}:
        return MockSpeechRecognizer(
            language=settings.voice.stt.language or None,
        )
    if engine in {"faster-whisper", "faster_whisper", "whisper"}:
        from .speech.faster_whisper import FasterWhisperRecognizer

        return FasterWhisperRecognizer(
            model=settings.voice.stt.model or "small",
            device=settings.voice.stt.device or "cpu",
            compute_type=settings.voice.stt.compute_type or "int8",
            language=settings.voice.stt.language or None,
        )

    raise _unsupported(engine, "stt")


def create_speaker_identifier() -> SpeakerIdentifier:
    """Build the configured speaker identification engine."""
    engine = (settings.voice.speaker.engine or "mock").lower()

    if engine in {"mock", ""}:
        return MockSpeakerIdentifier(
            confidence=settings.voice.speaker.confidence,
        )
    if engine in {"embedding", "speechbrain", "ecapa"}:
        from .speaker.embeddings import SpeechBrainEmbeddingProvider
        from .speaker.identifier import EmbeddingSpeakerIdentifier
        from .speaker.store import SpeakerStore

        threshold = (
            settings.voice.speaker.threshold or settings.voice.speaker.confidence
        )
        store_path = Path(settings.paths.data) / "voice" / "speakers.json"
        return EmbeddingSpeakerIdentifier(
            embedding_provider=SpeechBrainEmbeddingProvider(
                device=settings.voice.speaker.device or "cpu",
                model=settings.voice.speaker.model
                or "speechbrain/spkrec-ecapa-voxceleb",
            ),
            store=SpeakerStore(store_path),
            threshold=float(threshold),
            metric=settings.voice.speaker.metric or "cosine",
        )

    raise _unsupported(engine, "speaker")


def create_speaker_embedding_provider() -> SpeakerEmbeddingProvider:
    """Build the configured speaker embedding provider."""
    engine = (settings.voice.speaker.engine or "mock").lower()
    if engine in {"mock", ""}:
        return MockSpeakerEmbeddingProvider()
    if engine in {"embedding", "speechbrain", "ecapa"}:
        from .speaker.embeddings import SpeechBrainEmbeddingProvider

        return SpeechBrainEmbeddingProvider(device="cpu")
    raise _unsupported(engine, "speaker")


def create_tts() -> TextToSpeechProvider:
    """Build the configured text-to-speech engine."""
    engine = (settings.voice.tts.engine or "mock").lower()

    if engine in {"mock", ""}:
        return MockTextToSpeech(
            sample_rate=settings.voice.tts.sample_rate or settings.voice.sample_rate,
        )
    if engine in {"pyttsx3", "local"}:
        from .tts.pyttsx3_engine import Pyttsx3Engine

        return Pyttsx3Engine(
            voice=settings.voice.tts.voice or "",
            sample_rate=settings.voice.tts.sample_rate or settings.voice.sample_rate,
        )

    raise _unsupported(engine, "tts")


def create_audio_input(segments: list[AudioData] | None = None) -> AudioInputProvider:
    """Build the configured audio input engine (default mock for safety)."""
    engine = (settings.voice.input_engine or "mock").lower()
    if engine in {"mock", ""}:
        return MockAudioInput(segments or [])
    if engine in {"sounddevice", "microphone", "real"}:
        return create_real_audio_input()
    raise _unsupported(engine, "audio input")


def create_real_audio_input(
    sample_rate: int | None = None,
    channels: int | None = None,
    block_size: int | None = None,
    device: int | None = None,
) -> AudioInputProvider:
    """Build the real sounddevice microphone input (explicit opt-in)."""
    from .input.sounddevice_input import SoundDeviceInputProvider

    return SoundDeviceInputProvider(
        sample_rate=sample_rate or settings.voice.sample_rate,
        channels=channels or settings.voice.channels,
        block_size=block_size or settings.voice.block_size,
        device=device,
    )


def create_audio_output() -> AudioOutputProvider:
    """Build the configured audio output engine (default mock for safety)."""
    engine = (settings.voice.output_engine or "mock").lower()
    if engine in {"mock", ""}:
        return MockAudioOutput()
    if engine in {"sounddevice", "real"}:
        return create_real_audio_output()
    raise _unsupported(engine, "audio output")


def create_real_audio_output(
    sample_rate: int | None = None,
    channels: int | None = None,
) -> AudioOutputProvider:
    """Build the real sounddevice output (explicit opt-in)."""
    from .output.sounddevice_output import SoundDeviceOutputProvider

    return SoundDeviceOutputProvider(
        sample_rate=sample_rate or settings.voice.sample_rate,
        channels=channels or settings.voice.channels,
    )


def create_wake_word_detector() -> WakeWordDetector:
    """Build the configured wake-word detector."""
    engine = (settings.voice.wake.engine or "mock").lower()
    phrases = (settings.voice.wake_word or "hey asis",)
    if engine in {"mock", "", "keyphrase", "text"}:
        return MockWakeWordDetector(phrases=phrases)
    if engine in {"openwakeword", "open_wake_word", "audio"}:
        from .engines.openwakeword import OpenWakeWordDetector

        return OpenWakeWordDetector(
            phrases=phrases,
            threshold=float(settings.voice.wake.threshold),
            model_path=settings.voice.wake.model or None,
        )
    raise _unsupported(engine, "wake")


def create_vad() -> VadDetector:
    """Build the configured VAD detector."""
    engine = (settings.voice.vad.engine or "mock").lower()
    if engine in {"mock", ""}:
        return MockVadDetector()
    if engine in {"silero", "silero-vad", "silero_vad"}:
        from .input.vad import SileroVadDetector

        return SileroVadDetector(
            sample_rate=settings.voice.sample_rate,
            threshold=float(settings.voice.vad.threshold),
        )
    raise _unsupported(engine, "vad")


def create_voice_engines() -> dict:
    """Build every voice engine from the current settings."""
    logger = get_logger("voice.factory")

    engines = {
        "audio_input": create_audio_input(),
        "vad": create_vad(),
        "wake_word": create_wake_word_detector(),
        "speech_recognizer": create_speech_recognizer(),
        "speaker_identifier": create_speaker_identifier(),
        "tts": create_tts(),
        "audio_output": create_audio_output(),
    }

    for kind, engine in engines.items():
        logger.debug("Voice engine: %s -> %s", kind, type(engine).__name__)

    return engines
