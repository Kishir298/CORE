"""Voice -> AssistantApp integration (mock AI, real memory/tools/modes).

Covers: shared provider/model, memory recall, tools, general+coding modes.
No hardware, no network.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from asis.ai import AIManager
from asis.ai.providers import MockAIProvider
from asis.app.assistant import AssistantApp
from asis.app.modes import AssistantMode
from asis.cli.main import build_memory
from asis.identity import build_identity
from asis.voice.engines.mock import (
    MockAudioInput,
    MockAudioOutput,
    MockSpeakerIdentifier,
    MockSpeechRecognizer,
    MockTextToSpeech,
    MockVadDetector,
)
from asis.voice.models import AudioData
from asis.voice.pipeline import VoicePipeline
from asis.voice.runner import VoiceRunner, VoiceRunnerConfig


def _app(mode="general"):
    tmp = Path(tempfile.mkdtemp()) / "m.db"
    ai = AIManager(provider=MockAIProvider(model="shared-model"))
    mem = build_memory(tmp)
    return AssistantApp(identity=build_identity(), ai=ai, memory=mem, mode=mode)


def _pipe_for(text: str):
    return VoicePipeline(
        MockAudioInput([AudioData(samples=[1])]),
        MockSpeechRecognizer(text=text),
        MockSpeakerIdentifier(),
        MockTextToSpeech(),
        MockAudioOutput(),
        vad=MockVadDetector(),
        wake_word_detector=None,
    )


def test_voice_uses_shared_app_memory():
    app = _app()
    pipe = _pipe_for("My name is Rishik.")
    out = pipe.run_once(process_fn=lambda t, s: app.chat(t))
    assert out["status"] == "spoken"
    assert "Rishik" in " ".join(m.content for m in app.session.messages)


def test_voice_tool_cycle():
    app = _app()
    pipe = _pipe_for("what time is it")
    out = pipe.run_once(process_fn=lambda t, s: app.chat(t))
    assert out["response"]


def test_voice_coding_mode_shared_provider():
    app = _app(mode="coding")
    assert app.mode is AssistantMode.CODING
    provider_before = app.ai.provider
    pipe = _pipe_for("hello")
    out = pipe.run_once(process_fn=lambda t, s: app.chat(t))
    assert out["status"] == "spoken"
    assert app.ai.provider is provider_before
    assert app.mode is AssistantMode.CODING


def test_runner_explicit_mode_switch_authoritative():
    app = _app(mode="general")
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
        pipe, app=app, config=VoiceRunnerConfig(require_wake_word=False, max_turns=1)
    )
    from asis.system.context import RuntimeContext

    ctx = RuntimeContext()
    runner.start(ctx)
    try:
        runner.run()
    finally:
        runner.stop(ctx)
    assert app.mode is AssistantMode.CODING
