"""VoiceRunner + CORE: transcripts reach AssistantApp.chat() (incl. core:)."""

from __future__ import annotations

from asis.ai import AIManager
from asis.ai.providers import MockAIProvider
from asis.app import AssistantApp
from asis.identity import build_identity
from asis.integrations.core.connection import CoreConnectionManager
from asis.integrations.core.mock import MockCoreAdapter
from asis.system.context import RuntimeContext
from asis.tools.executor import ToolExecutor
from asis.tools.provided import register_core_tools
from asis.tools.registry import ToolRegistry
from asis.tools.router import ToolRouter
from asis.voice import (
    MockAudioInput,
    MockAudioOutput,
    MockSpeakerIdentifier,
    MockSpeechRecognizer,
    MockTextToSpeech,
    VoicePipeline,
    VoiceRunner,
    VoiceRunnerConfig,
)
from asis.voice.models import AudioData


def _pipeline(transcript="hello voice"):
    tts = MockTextToSpeech()
    pipe = VoicePipeline(
        MockAudioInput([AudioData(samples=[0], sample_rate=16000)]),
        MockSpeechRecognizer(text=transcript),
        MockSpeakerIdentifier(),
        tts,
        MockAudioOutput(),
    )
    return pipe, tts


def _app(memory_manager, responses=("hi via voice",), core=None, router=None):
    return AssistantApp(
        identity=build_identity(),
        ai=AIManager(provider=MockAIProvider(responses=list(responses))),
        memory=memory_manager,
        tools_router=router,
        core=core,
    )


def _online_stack():
    mock = MockCoreAdapter()
    manager = CoreConnectionManager(
        mock, enabled=True, credential_provider=lambda: "cred",
        reconnect_enabled=False,
    )
    registry = ToolRegistry()
    register_core_tools(registry, manager)
    router = ToolRouter(registry, ToolExecutor(authorizer=lambda tool: True))
    return manager, router


def _run(pipe, app, **cfg):
    config = VoiceRunnerConfig(require_wake_word=False, max_turns=1, **cfg)
    return VoiceRunner(pipe, app, config=config).run()


def test_voice_roundtrip_speaks_local_reply(memory_manager):
    pipe, tts = _pipeline()
    summary = _run(pipe, _app(memory_manager))
    assert summary["turns"] == 1
    assert tts.synthesized == ["hi via voice"]


def test_voice_core_intent_reaches_same_tool(memory_manager):
    manager, router = _online_stack()
    ctx = RuntimeContext()
    manager.start(ctx)
    try:
        pipe, tts = _pipeline("core:devices")
        summary = _run(pipe, _app(memory_manager, core=manager, router=router))
        assert summary["turns"] == 1
        assert "core_discover_devices: ok" in tts.synthesized[0]
    finally:
        manager.stop(ctx)


def test_voice_core_failure_is_spoken_safe(memory_manager):
    manager, router = _online_stack()  # offline
    pipe, tts = _pipeline("core:devices")
    _run(pipe, _app(memory_manager, core=manager, router=router))
    assert "CORE_UNAVAILABLE" in tts.synthesized[0]


def test_voice_has_no_core_networking():
    import pathlib

    text = (
        pathlib.Path(__file__).resolve().parents[1]
        / "asis"
        / "voice"
        / "runner.py"
    ).read_text()
    assert "core_device_client" not in text
    assert "from core." not in text
    assert "socket" not in text
