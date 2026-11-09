"""Offline-first capability: A.S.I.S. must run with no public internet.

Simulates offline conditions deterministically (no machine networking is
touched): DNS fails for every public hostname while loopback keeps real
semantics, so a missing local Ollama fails fast with a deterministic
error instead of hanging.

Covers: startup/wiring, local conversation, memory, local tools, coding
mode, voice architecture init, CORE-disabled mode, native tool calling,
web failure isolation, no runtime model downloads, and a guard against
hidden network dependencies. Live web stays opt-in (test_web_live.py).
"""

from __future__ import annotations

import socket
import sys
import types
from pathlib import Path

import pytest
import requests

from asis.ai import AIManager
from asis.ai.providers import MockAIProvider
from asis.ai.providers.ollama import AVAILABILITY_PROBE_TIMEOUT, OllamaProvider
from asis.app import AssistantApp
from asis.app.assistant import build_coding_tool_router, build_default_tool_router
from asis.coding.workspace import CodingWorkspace
from asis.configuration.settings import load_settings
from asis.errors import (
    InferenceError,
    SpeakerRecognitionError,
    SpeechRecognitionError,
    VoiceError,
)
from asis.identity import build_identity
from asis.tools.executor import ToolExecutor
from asis.tools.provided import CurrentTimeTool, EchoTool
from asis.tools.registry import ToolRegistry
from asis.tools.router import ToolRouter
from asis.voice.model_cache import model_missing_message


@pytest.fixture(autouse=True)
def no_internet(monkeypatch):
    """Fail DNS for public hosts; loopback keeps real semantics."""
    real_getaddrinfo = socket.getaddrinfo

    def _offline_getaddrinfo(host, port, *args, **kwargs):
        name = str(host).lower().rstrip(".")
        if name in ("localhost", "127.0.0.1", "::1"):
            return real_getaddrinfo(host, port, *args, **kwargs)
        raise socket.gaierror(8, "nodename nor servname provided, or not known")

    monkeypatch.setattr(socket, "getaddrinfo", _offline_getaddrinfo)


def _app(memory_manager, provider, router=None, **kw):
    return AssistantApp(
        identity=build_identity(),
        ai=AIManager(provider=provider),
        memory=memory_manager,
        tools_router=router,
        **kw,
    )


# -- startup / wiring ------------------------------------------------------


def test_offline_startup_wiring(memory_manager):
    """Core singletons construct without any network access."""
    identity = build_identity()
    app = _app(memory_manager, MockAIProvider(responses=("hi",)))
    assert identity.name
    assert app.chat("hello") == "hi"
    assert load_settings().ai.provider in ("mock", "ollama")


def test_offline_ollama_unreachable_is_deterministic():
    """Down local server -> fast False + deterministic error, no fallback."""
    provider = OllamaProvider(host="http://127.0.0.1:9", timeout=2.0)
    assert provider.available() is False
    with pytest.raises(InferenceError, match="Could not communicate with Ollama"):
        provider.chat([])


def test_offline_availability_probe_is_capped(monkeypatch):
    """The implicit probe never blocks on the long inference timeout."""
    seen = {}

    class _Resp:
        ok = True

    def _fake_get(url, timeout=None):
        seen["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(requests, "get", _fake_get)
    assert OllamaProvider(timeout=120.0).available() is True
    assert seen["timeout"] == AVAILABILITY_PROBE_TIMEOUT
    assert AVAILABILITY_PROBE_TIMEOUT <= 5.0


def test_offline_no_cloud_fallback_on_unknown_provider():
    from asis.ai.manager import create_provider

    with pytest.raises(InferenceError):
        create_provider("openai")


# -- local conversation / memory / tools ------------------------------------


def test_offline_conversation_and_memory(memory_manager):
    app = _app(memory_manager, MockAIProvider(responses=("local reply",)))
    assert app.chat("remember the sky is blue") == "local reply"
    memory_manager.remember("the sky is blue", importance=9)
    assert "blue" in (memory_manager.search_context("sky color") or "")


def test_offline_local_tools(memory_manager):
    router = build_default_tool_router()
    assert router.execute("echo", text="hi").success is True
    assert router.execute("current_time").success is True
    assert "web_search" in router.registry.list_names()  # registered, gated below


def test_offline_coding_mode(memory_manager, tmp_path):
    workspace = CodingWorkspace(tmp_path.resolve())
    (tmp_path / "notes.txt").write_text("offline notes")
    router = build_coding_tool_router(workspace)
    assert router.execute("read_file", path="notes.txt").success is True
    assert router.execute("list_directory", path=".").success is True
    assert {"web_search", "web_fetch"} <= set(router.registry.list_names())


def test_offline_native_tool_calling(memory_manager):
    ai = MockAIProvider(
        responses=("", "done."),
        tool_sequences=[[{"name": "echo", "arguments": {"text": "x"}}], None],
    )
    registry = ToolRegistry()
    registry.register(EchoTool())
    registry.register(CurrentTimeTool())
    router = ToolRouter(registry, ToolExecutor(authorizer=lambda tool: True))
    assert _app(memory_manager, ai, router=router).chat("run echo x") == "done."


# -- voice architecture -------------------------------------------------------


def test_offline_voice_pipeline_initializes_and_runs(memory_manager):
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

    ai = MockAIProvider(responses=("spoken.",))
    app = _app(memory_manager, ai)
    tts = MockTextToSpeech()
    pipe = VoicePipeline(
        MockAudioInput([AudioData(samples=[0], sample_rate=16000)]),
        MockSpeechRecognizer(text="hi"),
        MockSpeakerIdentifier(),
        tts,
        MockAudioOutput(),
    )
    summary = VoiceRunner(
        pipe, app, config=VoiceRunnerConfig(require_wake_word=False, max_turns=1)
    ).run()
    assert summary["turns"] == 1
    assert tts.synthesized == ["spoken."]


def test_offline_voice_model_loaders_report_not_installed(monkeypatch):
    """Missing cached weights -> MODEL_NOT_INSTALLED, never a download loop."""
    assert "MODEL_NOT_INSTALLED" in model_missing_message(
        engine="STT", model="small", setting="ASIS_VOICE_STT_ENGINE"
    )

    fake_fw = types.ModuleType("faster_whisper")

    class _BoomModel:
        def __init__(self, *args, **kwargs):
            raise ConnectionError("offline")

    fake_fw.WhisperModel = _BoomModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_fw)
    from asis.voice.speech.speech_to_text import SpeechTranscriber

    with pytest.raises(SpeechRecognitionError, match="MODEL_NOT_INSTALLED"):
        SpeechTranscriber(model_size="small")

    # Missing package entirely -> install hint, still no download attempt.
    # (Block the real import so this holds with or without voice extras.)
    monkeypatch.delitem(sys.modules, "faster_whisper", raising=False)

    class _Blocker:
        def find_spec(self, name, path=None, target=None):
            if name == "faster_whisper" or name.startswith("faster_whisper."):
                raise ImportError("No module named faster_whisper (test-blocked)")

    blocker = _Blocker()
    sys.meta_path.insert(0, blocker)
    try:
        with pytest.raises(SpeechRecognitionError, match="not installed"):
            SpeechTranscriber(model_size="small")
    finally:
        sys.meta_path.remove(blocker)


def test_offline_speaker_vad_wake_report_not_installed(monkeypatch):
    fake_sb = types.ModuleType("speechbrain")
    fake_sb_inf = types.ModuleType("speechbrain.inference")
    fake_sb_spk = types.ModuleType("speechbrain.inference.speaker")

    class _Encoder:
        @staticmethod
        def from_hparams(**kwargs):
            raise OSError("offline")

    fake_sb_spk.EncoderClassifier = _Encoder
    monkeypatch.setitem(sys.modules, "speechbrain", fake_sb)
    monkeypatch.setitem(sys.modules, "speechbrain.inference", fake_sb_inf)
    monkeypatch.setitem(sys.modules, "speechbrain.inference.speaker", fake_sb_spk)
    from asis.voice.speaker.embeddings import SpeechBrainEmbeddingProvider

    with pytest.raises(SpeakerRecognitionError, match="MODEL_NOT_INSTALLED"):
        SpeechBrainEmbeddingProvider()

    fake_torch = types.ModuleType("torch")
    fake_torch.device = lambda name: name
    fake_silero = types.ModuleType("silero_vad")
    fake_silero.load_silero_vad = lambda **kwargs: (_ for _ in ()).throw(
        RuntimeError("offline")
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "silero_vad", fake_silero)
    from asis.voice.input.vad import VoiceActivityDetector

    with pytest.raises(VoiceError, match="MODEL_NOT_INSTALLED"):
        VoiceActivityDetector()

    fake_oww = types.ModuleType("openwakeword")
    fake_oww_model = types.ModuleType("openwakeword.model")

    class _WakeModel:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("offline")

    fake_oww_model.Model = _WakeModel
    monkeypatch.setitem(sys.modules, "openwakeword", fake_oww)
    monkeypatch.setitem(sys.modules, "openwakeword.model", fake_oww_model)
    from asis.voice.engines.openwakeword import OpenWakeWordDetector

    with pytest.raises(VoiceError, match="MODEL_NOT_INSTALLED"):
        OpenWakeWordDetector()


# -- CORE-disabled --------------------------------------------------------------


def test_offline_core_disabled_is_standalone(memory_manager):
    from asis.integrations.core.connection import CoreConnectionManager
    from asis.integrations.core.mock import MockCoreAdapter
    from asis.system.context import RuntimeContext

    manager = CoreConnectionManager(MockCoreAdapter(), enabled=False)
    ctx = RuntimeContext()
    manager.start(ctx)
    try:
        assert manager.is_available() is False
        app = _app(memory_manager, MockAIProvider(responses=("ok",)))
        assert "disabled" in app.core_status_text().lower()
        assert app.chat("hi") == "ok"
    finally:
        manager.stop(ctx)


# -- web isolation ---------------------------------------------------------------


def test_offline_web_search_fails_but_local_survives(memory_manager):
    """Public DNS fails -> web errors are WEB_*, local tools/chat unaffected."""
    router = build_default_tool_router()
    failed = router.execute("web_search", query="offline query")
    assert failed.success is False
    assert failed.error.startswith("WEB_")
    assert router.execute("echo", text="still here").success is True

    ai = MockAIProvider(
        responses=("", "local answer."),
        tool_sequences=[
            [{"name": "web_search", "arguments": {"query": "offline query"}}],
            None,
        ],
    )
    app = _app(memory_manager, ai)
    assert app.chat("search please") == "local answer."


def test_offline_web_disabled_keeps_everything_local(memory_manager, monkeypatch):
    import sys as _sys

    module = _sys.modules["asis.configuration.settings"]
    monkeypatch.setattr(
        module, "settings", load_settings({"ASIS_WEB_ENABLED": "false"})
    )
    router = build_default_tool_router()
    assert router.execute("web_fetch", url="https://example.com/").error.startswith(
        "WEB_DISABLED"
    )
    assert router.execute("current_time").success is True


# -- no hidden network activity ----------------------------------------------------


def test_offline_no_hidden_network_dependencies():
    """Only Ollama-loopback and the web boundary may touch the network."""
    root = Path(__file__).resolve().parent.parent / "asis"
    request_users = set()
    socket_users = set()
    banned: list[str] = []
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(root)).replace("\\", "/")
        if "import requests" in text or "from requests" in text:
            request_users.add(rel)
        if "import socket" in text or "from socket" in text:
            socket_users.add(rel)
        for token in (
            "telemetry",
            "analytics",
            "sentry",
            "posthog",
            "mixpanel",
            "api.openai",
            "api.anthropic",
            "generativelanguage",
        ):
            if token in text.lower():
                banned.append(f"{rel}: {token}")
    assert request_users == {
        "ai/providers/ollama.py",
        "web/provider.py",
        "update/detectors.py",
    }, request_users
    assert socket_users == {"web/security.py", "update/detectors.py"}, socket_users
    assert banned == []

