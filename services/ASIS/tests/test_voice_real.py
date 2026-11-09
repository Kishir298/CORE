"""Optional real-provider smoke tests (hardware/model-free by default).

Run with ASIS_REAL_VOICE_TESTS=1. Never require microphone, speakers,
GPU, or network. Each test skips gracefully when the optional dependency
is missing. Synthetic audio only; no accuracy claims.
"""

from __future__ import annotations

import os

import pytest

from asis.errors import VoiceError

REAL = os.environ.get("ASIS_REAL_VOICE_TESTS") == "1"
needs_real = pytest.mark.skipif(not REAL, reason="set ASIS_REAL_VOICE_TESTS=1")


def _sine(samples: int = 1600, freq: float = 440.0, rate: int = 16000) -> list[float]:
    import math

    return [0.3 * math.sin(2 * math.pi * freq * i / rate) for i in range(samples)]


@needs_real
def test_real_vad_accepts_synthetic():
    from asis.voice.input.vad import SileroVadDetector
    from asis.voice.models import AudioData

    try:
        vad = SileroVadDetector()
    except Exception as exc:
        pytest.skip(f"VAD unavailable: {exc}")
    audio = AudioData(samples=_sine(), sample_rate=16000)
    assert isinstance(vad.is_speech(audio), bool)


@needs_real
def test_real_wake_loads_and_accepts_audio():
    from asis.voice.engines.openwakeword import OpenWakeWordDetector
    from asis.voice.models import AudioData

    try:
        det = OpenWakeWordDetector()
    except Exception as exc:
        pytest.skip(f"wake engine unavailable: {exc}")
    audio = AudioData(samples=_sine(), sample_rate=16000)
    assert isinstance(det.detect(audio), bool)


@needs_real
def test_real_stt_empty_audio():
    from asis.voice.models import AudioData
    from asis.voice.speech.faster_whisper import FasterWhisperRecognizer

    try:
        rec = FasterWhisperRecognizer(model="tiny")
    except Exception as exc:
        pytest.skip(f"STT unavailable: {exc}")
    out = rec.transcribe(AudioData(samples=[0.0] * 1600, sample_rate=16000))
    assert isinstance(out.text, str)


@needs_real
def test_real_tts_synth():
    from asis.voice.tts.pyttsx3_engine import Pyttsx3Engine

    try:
        engine = Pyttsx3Engine()
    except Exception as exc:
        pytest.skip(f"TTS unavailable: {exc}")
    audio = engine.synthesize("A.S.I.S. smoke test.")
    assert len(list(audio.samples)) > 0
    assert audio.sample_rate > 0


@needs_real
def test_real_audio_io_init():
    from asis.voice.factory import create_real_audio_input, create_real_audio_output
    from asis.voice.models import AudioData

    try:
        inp = create_real_audio_input()
        outp = create_real_audio_output()
    except Exception as exc:
        pytest.skip(f"audio IO unavailable: {exc}")
    # Init-only: do not require live mic/speakers in CI.
    assert inp is not None and outp is not None
    with pytest.raises(VoiceError):
        outp.play(AudioData(samples=[]))


@needs_real
def test_real_speaker_embedding_contract():
    from asis.voice.models import AudioData
    from asis.voice.speaker.embeddings import SpeechBrainEmbeddingProvider

    try:
        provider = SpeechBrainEmbeddingProvider()
    except Exception as exc:
        pytest.skip(f"speaker engine unavailable: {exc}")
    emb = provider.embed(AudioData(samples=_sine(), sample_rate=16000))
    assert isinstance(emb, list) and len(emb) > 0
