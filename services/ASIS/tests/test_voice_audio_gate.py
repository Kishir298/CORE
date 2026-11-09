"""Audio-first wake gating, utterance capture, runner, mode commands.

Mock-only, no hardware/models/network.
"""

from __future__ import annotations

import pytest

from asis.app.modes import AssistantMode
from asis.errors import CancellationError
from asis.events.bus import EventBus
from asis.events.events import EventType
from asis.system.context import RuntimeContext
from asis.system.interrupt import InterruptCoordinator
from asis.voice.commands import parse_voice_mode_command
from asis.voice.engines.mock import (
    MockAudioInput,
    MockAudioOutput,
    MockSpeakerIdentifier,
    MockSpeechRecognizer,
    MockTextToSpeech,
    MockVadDetector,
    MockWakeWordDetector,
)
from asis.voice.input.utterance import UtteranceConfig, capture_utterance
from asis.voice.models import AudioData
from asis.voice.pipeline import VoicePipeline
from asis.voice.runner import VoiceRunner, VoiceRunnerConfig


def _pipe(**over):
    kw = {
        "audio_input": MockAudioInput([AudioData(samples=[1, 2])]),
        "speech_recognizer": MockSpeechRecognizer(text="hey asis go"),
        "speaker_identifier": MockSpeakerIdentifier(),
        "tts": MockTextToSpeech(),
        "audio_output": MockAudioOutput(),
        "vad": MockVadDetector(default=True),
        "wake_word_detector": MockWakeWordDetector(),
    }
    kw.update(over)
    return VoicePipeline(**kw)


def test_audio_gate_miss_skips_stt():
    stt = MockSpeechRecognizer(text="hey asis go")
    pipe = _pipe(
        speech_recognizer=stt,
        wake_word_detector=MockWakeWordDetector(results=[False]),
    )
    out = pipe.run_once(require_wake_word=True)
    assert out["status"] == "no-wake-word"
    assert out["text"] == ""
    assert stt.transcribed == []


def test_audio_gate_hit_then_text_reject():
    stt = MockSpeechRecognizer(text="hello no wake")
    pipe = _pipe(
        speech_recognizer=stt,
        wake_word_detector=MockWakeWordDetector(
            phrases=("hey asis",), results=[True]
        ),
    )
    out = pipe.run_once(require_wake_word=True)
    assert out["status"] == "no-wake-word"
    assert out["text"] == "hello no wake"
    assert len(stt.transcribed) == 1


def test_vad_and_assistant_events():
    bus = EventBus()
    seen: dict[str, dict] = {}

    def rec(e):
        seen[e.type.value] = e.data

    for et in EventType:
        bus.subscribe(et, rec)
    pipe = VoicePipeline(
        MockAudioInput([AudioData(samples=[1])]),
        MockSpeechRecognizer(text="hey asis hi"),
        MockSpeakerIdentifier(),
        MockTextToSpeech(),
        MockAudioOutput(),
        event_bus=bus,
        vad=MockVadDetector(default=True),
        wake_word_detector=MockWakeWordDetector(),
    )
    pipe.run_once(process_fn=lambda t, s: "ok", require_wake_word=True)
    assert "voice.vad" in seen
    assert "voice.assistant.started" in seen
    assert "voice.assistant.finished" in seen
    assert "voice.wake_word.detected" in seen


def test_interrupted_event_on_cancel():
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe(EventType.VOICE_INTERRUPTED, lambda e: seen.append(e.type.value))
    ic = InterruptCoordinator()
    ic.register("voice")
    ic.cancel("voice")
    pipe = _pipe(interrupts=ic, event_bus=bus)
    with pytest.raises(CancellationError):
        pipe.run_once()
    assert seen == ["voice.interrupted"]


def test_utterance_capture_bounded():
    cfg = UtteranceConfig(
        sample_rate=10, max_utterance_seconds=1.0, silence_seconds=0.2,
        max_initial_silence_seconds=0.3, block_size=2,
    )
    inp = MockAudioInput(
        [AudioData(samples=[1, 1]), AudioData(samples=[0, 0]), AudioData(samples=[])]
    )
    out = capture_utterance(
        inp, vad=MockVadDetector(results=[True, False, False]),
        seed=AudioData(samples=[9, 9], sample_rate=10), config=cfg,
    )
    assert out.samples[:2] == [9.0, 9.0]
    assert len(out.samples) <= 10
    # Empty input without VAD stays bounded.
    inp2 = MockAudioInput([AudioData(samples=[5])])
    out2 = capture_utterance(inp2, vad=None, seed=AudioData(samples=[1]))
    assert len(out2.samples) == 2


def test_utterance_config_validation():
    with pytest.raises(ValueError):
        UtteranceConfig(max_utterance_seconds=0)
    with pytest.raises(ValueError):
        UtteranceConfig(silence_seconds=0)


def test_voice_mode_commands():
    assert parse_voice_mode_command("switch to coding mode") is AssistantMode.CODING
    assert parse_voice_mode_command("Switch to General Mode") is AssistantMode.GENERAL
    assert parse_voice_mode_command("hello world") is None
    assert parse_voice_mode_command("") is None


def test_runner_mode_switch_and_shutdown():
    import tempfile
    from pathlib import Path

    from asis.ai import AIManager
    from asis.ai.providers import MockAIProvider
    from asis.app.assistant import AssistantApp
    from asis.cli.main import build_memory
    from asis.identity import build_identity

    tmp = Path(tempfile.mkdtemp()) / "m.db"
    ai = AIManager(provider=MockAIProvider(model="m"))
    mem = build_memory(tmp)
    app = AssistantApp(identity=build_identity(), ai=ai, memory=mem, mode="general")
    pipe = VoicePipeline(
        MockAudioInput([AudioData(samples=[1]), AudioData(samples=[1])]),
        MockSpeechRecognizer(text="switch to coding mode"),
        MockSpeakerIdentifier(),
        MockTextToSpeech(),
        MockAudioOutput(),
        vad=MockVadDetector(),
        wake_word_detector=None,
    )
    runner = VoiceRunner(
        pipe, app=app,
        config=VoiceRunnerConfig(require_wake_word=False, max_turns=1),
    )
    ctx = RuntimeContext()
    runner.start(ctx)
    try:
        summary = runner.run()
    finally:
        runner.stop(ctx)
    assert app.mode is AssistantMode.CODING
    assert summary["turns"] == 1


def test_runner_lifecycle_component():
    pipe = _pipe()
    runner = VoiceRunner(pipe, app=None, config=VoiceRunnerConfig(max_turns=0))
    ctx = RuntimeContext()
    runner.start(ctx)
    assert pipe.audio_input.started is True
    runner.stop(ctx)
    assert pipe.audio_input.stopped is True
    assert pipe.audio_output.stopped is True


def test_runner_speaker_prefix():
    seen: list[str] = []

    class FakeApp:
        def chat(self, message: str) -> str:
            seen.append(message)
            return "ok"

    from asis.voice.models import SpeakerResult

    pipe = _pipe()
    runner = VoiceRunner(pipe, app=FakeApp())
    out = runner._process("hi", SpeakerResult(speaker_id="bob", is_known=True))
    assert out == "ok"
    assert seen == ["[bob] hi"]
    seen.clear()
    runner._process("hi", SpeakerResult(speaker_id="unknown", is_known=False))
    assert seen == ["hi"]
