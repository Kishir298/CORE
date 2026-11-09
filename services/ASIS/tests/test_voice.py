"""
Comprehensive voice tests (mock-only, no hardware/models/network).

Covers: models, input/buffer/VAD, STT, speaker, wake word, TTS,
output, pipeline ordering, interruption, events, CLI.
"""

from __future__ import annotations

import dataclasses
import sys

import pytest

from asis.cli.voice import run_voice_once
from asis.errors import (
    CancellationError,
    SpeakerRecognitionError,
    SpeechRecognitionError,
    TTSError,
    VoiceError,
)
from asis.events.bus import EventBus
from asis.events.events import EventType
from asis.system.interrupt import InterruptCoordinator
from asis.voice.engines.mock import (
    MockAudioInput,
    MockAudioOutput,
    MockSpeakerEmbeddingProvider,
    MockSpeakerIdentifier,
    MockSpeechRecognizer,
    MockTextToSpeech,
    MockVadDetector,
    MockWakeWordDetector,
)
from asis.voice.engines.wakeword import KeyphraseWakeWordDetector
from asis.voice.input.audio_buffer import AudioBuffer
from asis.voice.models import AudioData, SpeakerResult, TranscriptionResult, VoiceEvent
from asis.voice.pipeline import VoicePipeline
from asis.voice.speaker.embeddings import (
    best_match,
    cosine_similarity,
    mean_embedding,
)
from asis.voice.speaker.identifier import EmbeddingSpeakerIdentifier
from asis.voice.speaker.profile import SpeakerProfile
from asis.voice.speaker.registration import register_speaker
from asis.voice.speaker.store import SpeakerStore


def _pipe(**over):
    kw = {
        "audio_input": MockAudioInput([AudioData(samples=[1, 2])]),
        "speech_recognizer": MockSpeechRecognizer(text="hello"),
        "speaker_identifier": MockSpeakerIdentifier(),
        "tts": MockTextToSpeech(),
        "audio_output": MockAudioOutput(),
    }
    kw.update(over)
    return VoicePipeline(**kw)


# -- models ------------------------------------------------------------
def test_audio_defaults_and_validation():
    a = AudioData(samples=[])
    assert a.sample_rate == 16_000 and a.channels == 1 and a.metadata == {}
    assert dataclasses.is_dataclass(a)
    with pytest.raises(ValueError):
        AudioData(samples=[], sample_rate=0)
    with pytest.raises(ValueError):
        AudioData(samples=[], channels=0)


def test_transcription_speaker_validation():
    assert TranscriptionResult(text="hi").language is None
    with pytest.raises(ValueError):
        TranscriptionResult(text=123)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        TranscriptionResult(text="hi", confidence=2.0)
    assert SpeakerResult(speaker_id="a").is_known is False
    with pytest.raises(ValueError):
        SpeakerResult(speaker_id=" ")


def test_voice_event_roundtrip_and_immutability():
    v = VoiceEvent(event_type=EventType.VOICE_INPUT, payload={"n": 1})
    assert v.source == "voice"
    e = v.to_event()
    assert e.type == EventType.VOICE_INPUT and e.source == "voice"
    v2 = VoiceEvent.from_event(e)
    assert v2.event_type == v.event_type
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.source = "x"  # type: ignore[misc]
    with pytest.raises(ValueError):
        VoiceEvent(event_type="bad")  # type: ignore[arg-type]


# -- input -------------------------------------------------------------
def test_audio_buffer_write_read_consume():
    b = AudioBuffer(max_seconds=1.0, sample_rate=10)
    b.write([1, 2, 3])
    assert b.sample_count == 3
    assert b.read() == [1.0, 2.0, 3.0]
    assert b.consume(seconds=0.2) == [2.0, 3.0]
    b.clear()
    assert b.sample_count == 0
    with pytest.raises(ValueError):
        AudioBuffer(max_seconds=0)


def test_mock_input_lifecycle():
    mic = MockAudioInput([AudioData(samples=[1])])
    mic.start()
    assert mic.started is True
    assert mic.read(99).samples == [1]
    assert mic.read(99).samples == []
    mic.stop()
    assert mic.stopped is True


def test_mock_vad_scripted():
    vad = MockVadDetector(results=[True, False])
    a = AudioData(samples=[1])
    assert vad.is_speech(a) is True
    assert vad.is_speech(a) is False
    assert vad.is_speech(a) is True  # default


def _block_imports(*names):
    """Context manager faking absent optional deps (works with voice extras installed)."""

    class _Blocker:
        def find_spec(self, name, path=None, target=None):
            if name in names or any(name.startswith(n + ".") for n in names):
                raise ImportError(f"No module named {name} (test-blocked)")

    blocker = _Blocker()

    class _Guard:
        def __enter__(self):
            self._saved = {}
            for mod in list(sys.modules):
                if mod in names or any(mod.startswith(n + ".") for n in names):
                    self._saved[mod] = sys.modules.pop(mod)
            sys.meta_path.insert(0, blocker)
            return self

        def __exit__(self, *args):
            sys.meta_path.remove(blocker)
            sys.modules.update(self._saved)
            return False

    return _Guard()


def test_microphone_missing_dep():
    from asis.voice.input.microphone import Microphone

    m = Microphone()
    # sounddevice unavailable -> helpful VoiceError, not crash
    with _block_imports("sounddevice"):
        try:
            m.start()
        except VoiceError:
            pass
        except Exception as exc:  # pragma: no cover
            pytest.fail(f"wrong error: {exc}")
    # not running -> RuntimeError
    with pytest.raises(RuntimeError):
        m.read()


def test_vad_missing_dep():
    from asis.voice.input.vad import VoiceActivityDetector

    with _block_imports("torch", "silero_vad"):
        with pytest.raises((VoiceError, ValueError)):
            VoiceActivityDetector()


# -- STT ---------------------------------------------------------------
def test_mock_stt_records_and_returns():
    r = MockSpeechRecognizer(text="hey", language="en", confidence=0.9)
    out = r.transcribe(AudioData(samples=[1]))
    assert out.text == "hey" and out.language == "en"
    assert len(r.transcribed) == 1


def test_real_stt_missing_dep_and_validation():
    from asis.voice.speech.faster_whisper import FasterWhisperRecognizer

    with _block_imports("faster_whisper"), pytest.raises(SpeechRecognitionError):
        FasterWhisperRecognizer(model="small")

    class FakeEngine:
        def transcribe(self, samples, sample_rate=16000):
            return TranscriptionResult(text="hi", confidence=0.5, duration=0.1)

    r = FasterWhisperRecognizer.__new__(FasterWhisperRecognizer)
    r._engine = FakeEngine()
    r._model_name = "small"
    r._device = "cpu"
    r._compute_type = "int8"
    r._language = None
    from asis.logging.logger import get_logger

    r._logger = get_logger("test")
    assert r.transcribe(AudioData(samples=[0.1])).text == "hi"
    with pytest.raises(SpeechRecognitionError):
        r.transcribe("bad")  # type: ignore[arg-type]


# -- speaker -----------------------------------------------------------
def test_profile_serialization():
    p = SpeakerProfile(speaker_id="a", name="A", embeddings=[[1.0, 0.0]])
    d = p.to_dict()
    assert SpeakerProfile.from_dict(d).speaker_id == "a"
    with pytest.raises(ValueError):
        SpeakerProfile(speaker_id=" ")


def test_store_register_get_delete(tmp_path):
    store = SpeakerStore(tmp_path / "s.json")
    store.register(SpeakerProfile(speaker_id="a", embeddings=[[1.0]]))
    assert store.get("a") is not None
    assert len(store.list_profiles()) == 1
    assert store.delete("a") is True
    assert store.delete("missing") is False
    # persistence
    store.register(SpeakerProfile(speaker_id="b", embeddings=[[0.0, 1.0]]))
    assert SpeakerStore(tmp_path / "s.json").get("b") is not None


def test_registration_and_matching():
    store = SpeakerStore()
    register_speaker(
        store,
        MockSpeakerEmbeddingProvider([1.0, 0.0]),
        "alice",
        [AudioData(samples=[1])],
    )
    assert store.get("alice") is not None
    assert cosine_similarity([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)
    assert mean_embedding([[1, 0], [0, 1]]) == [0.5, 0.5]
    assert best_match([1, 0], [("a", [1, 0]), ("b", [0, 1])]) == ("a", 1.0)
    ident = EmbeddingSpeakerIdentifier(
        MockSpeakerEmbeddingProvider([1.0, 0.0]), store, threshold=0.6
    )
    assert ident.identify(AudioData(samples=[1])).is_known is True
    ident2 = EmbeddingSpeakerIdentifier(
        MockSpeakerEmbeddingProvider([0.0, 1.0]), store, threshold=0.6
    )
    unknown = ident2.identify(AudioData(samples=[1]))
    assert unknown.speaker_id == "unknown" and unknown.is_known is False
    # empty store -> unknown, never false-positive
    empty = EmbeddingSpeakerIdentifier(
        MockSpeakerEmbeddingProvider([1.0, 0.0]), SpeakerStore(), threshold=0.99
    ).identify(AudioData(samples=[1]))
    assert empty.is_known is False


def test_speaker_embedding_missing_dep():
    from asis.voice.speaker.embeddings import SpeechBrainEmbeddingProvider

    with _block_imports("speechbrain"), pytest.raises(SpeakerRecognitionError):
        SpeechBrainEmbeddingProvider()


# -- wake word ---------------------------------------------------------
def test_keyphrase_detection_cases():
    k = KeyphraseWakeWordDetector(phrases=("hey asis", "ok asis"))
    assert k.detect("Hey ASIS turn on") is True
    assert k.detect("  hey asis  ") is True
    assert k.detect("hello world") is False
    assert k.detect("") is False
    assert k.strip_phrase("hey asis what time") == "what time"
    assert k.strip_phrase("nothing here") == "nothing here"


def test_mock_wake_scripted_and_text():
    w = MockWakeWordDetector(results=[True, False])
    a = AudioData(samples=[1])
    assert w.detect(a) is True
    assert w.detect(a) is False
    assert w.detect_text("hey asis hi") is True


def test_openwakeword_missing_dep():
    from asis.voice.engines.openwakeword import OpenWakeWordDetector

    with pytest.raises(VoiceError):
        OpenWakeWordDetector()


# -- TTS / output ------------------------------------------------------
def test_mock_tts_and_output():
    tts = MockTextToSpeech()
    audio = tts.synthesize("hello")
    assert isinstance(audio, AudioData) and audio.sample_rate == 16_000
    assert tts.synthesized == ["hello"]
    out = MockAudioOutput()
    out.play(audio)
    assert out.played == [audio]
    out.stop()
    assert out.stopped is True


def test_pyttsx3_missing_dep_and_validation():
    from asis.voice.tts.pyttsx3_engine import Pyttsx3Engine

    with _block_imports("pyttsx3"), pytest.raises(TTSError):
        Pyttsx3Engine()
    with pytest.raises(ValueError):
        Pyttsx3Engine(sample_rate=0)


def test_output_invalid_and_missing_dep():
    from asis.voice.output.sounddevice_output import SoundDeviceOutputProvider

    o = SoundDeviceOutputProvider()
    with pytest.raises(VoiceError):
        o.play(AudioData(samples=[]))
    with pytest.raises(VoiceError):
        o.play("bad")  # type: ignore[arg-type]


# -- pipeline ----------------------------------------------------------
def test_pipeline_ordering_and_provider_calls():
    audio = AudioData(samples=[1])
    tts = MockTextToSpeech()
    out = MockAudioOutput()
    stt = MockSpeechRecognizer(text="hey asis go")
    spk = MockSpeakerIdentifier(speaker_id="bob", confidence=0.8, is_known=True)
    pipe = VoicePipeline(
        MockAudioInput([audio]),
        stt,
        spk,
        tts,
        out,
        vad=MockVadDetector(default=True),
        wake_word_detector=MockWakeWordDetector(),
    )
    result = pipe.run_once(require_wake_word=False)
    assert result["status"] == "spoken" and result["text"] == "hey asis go"
    assert stt.transcribed and spk.identified and tts.synthesized and out.played


def test_pipeline_no_speech_and_no_wake():
    pipe = _pipe(vad=MockVadDetector(default=False))
    assert pipe.run_once()["status"] == "no-speech"
    pipe2 = VoicePipeline(
        MockAudioInput([AudioData(samples=[1])]),
        MockSpeechRecognizer(text="hello no wake"),
        MockSpeakerIdentifier(),
        MockTextToSpeech(),
        MockAudioOutput(),
        wake_word_detector=MockWakeWordDetector(phrases=("hey asis",)),
    )
    out = pipe2.run_once(require_wake_word=True)
    assert out["status"] == "no-wake-word"


def test_pipeline_interruption():
    ic = InterruptCoordinator()
    ic.register("voice")
    ic.cancel("voice")
    pipe = _pipe(interrupts=ic)
    with pytest.raises(CancellationError):
        pipe.listen()
    with pytest.raises(CancellationError):
        pipe.transcribe(AudioData(samples=[1]))
    with pytest.raises(CancellationError):
        pipe.speak("hi")


def test_pipeline_events_and_no_raw_audio():
    bus = EventBus()
    seen: dict[str, dict] = {}

    def rec(e):
        seen[e.type.value] = e.data

    for et in EventType:
        bus.subscribe(et, rec)
    pipe = VoicePipeline(
        MockAudioInput([AudioData(samples=[5])]),
        MockSpeechRecognizer(text="hey asis hi"),
        MockSpeakerIdentifier(speaker_id="x", is_known=True),
        MockTextToSpeech(),
        MockAudioOutput(),
        event_bus=bus,
        vad=MockVadDetector(default=True),
        wake_word_detector=MockWakeWordDetector(),
    )
    pipe.run_once(require_wake_word=True)
    for key in (
        "voice.input",
        "voice.stt.started",
        "voice.stt.ready",
        "voice.speaker.identified",
        "voice.wake_word.detected",
        "voice.tts.started",
        "voice.tts.finished",
        "voice.output",
    ):
        assert key in seen, key
    for payload in seen.values():
        assert "samples" not in payload and "embedding" not in payload


def test_voice_event_bus_compat():
    bus = EventBus()
    got = []
    bus.subscribe(EventType.VOICE_INPUT, got.append)
    v = VoiceEvent(event_type=EventType.VOICE_INPUT, payload={"n": 1})
    bus.publish(v.to_event())
    assert len(got) == 1


# -- CLI ---------------------------------------------------------------
def test_voice_once_helper():
    out = run_voice_once([AudioData(samples=[1])], transcript="hello")
    assert out["status"] == "spoken" and out["text"] == "hello"


def test_voice_cli_parsing():
    from asis.cli.voice import build_voice_parser

    args = build_voice_parser().parse_args(["--no-wake-word", "--stt-engine", "mock"])
    assert args.no_wake_word is True and args.stt_engine == "mock"


def test_main_entry_routes_voice(capsys):
    from asis.cli.main import entry

    assert entry(["--version"]) == 0
    assert "A.S.I.S." in capsys.readouterr().out


def test_voice_imports_stay_lazy():
    """Importing voice wiring must not pull heavy ML/audio libraries."""
    import subprocess
    import sys

    heavy = [
        "torch",
        "sounddevice",
        "faster_whisper",
        "speechbrain",
        "openwakeword",
        "silero",
    ]
    names = ", ".join(repr(m) for m in heavy)
    code = (
        "import sys;"
        "import asis.voice.factory, asis.voice.pipeline,"
        " asis.voice.runner, asis.cli.voice;"
        "loaded = [m for m in (" + names + ",) if m in sys.modules];"
        "assert not loaded, loaded;"
        "print('lazy-ok')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, proc.stderr
    assert "lazy-ok" in proc.stdout
