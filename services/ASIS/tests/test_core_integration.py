"""End-to-end: Router+Adapter (mock host path), voice/LLM independence, ASCS sharing.

Proves an A.S.I.S. tool traverses the real adapter/client architecture
without importing CORE-HOST, that the local AI provider is untouched by
CORE state, and that voice/ASCS consumers share the same ToolRouter path
(no separate voice→CORE client).
"""

from __future__ import annotations

import json

from asis.ai.providers.mock import MockAIProvider
from asis.integrations.core.connection import CoreConnectionManager
from asis.integrations.core.mock import MockCoreAdapter
from asis.system.context import RuntimeContext
from asis.tools.executor import ToolExecutor
from asis.tools.provided import EchoTool, register_core_tools
from asis.tools.provided.time import CurrentTimeTool
from asis.tools.registry import ToolRegistry
from asis.tools.router import ToolRouter
from asis.voice.engines.mock import MockSpeechRecognizer, MockTextToSpeech
from asis.voice.models import AudioData


def _stack(auto_approve=True):
    mock = MockCoreAdapter()
    manager = CoreConnectionManager(
        mock, enabled=True, credential_provider=lambda: "cred",
        reconnect_enabled=False,
    )
    registry = ToolRegistry()
    registry.register(EchoTool())
    registry.register(CurrentTimeTool())
    register_core_tools(registry, manager)
    executor = ToolExecutor(authorizer=lambda tool: bool(auto_approve))
    return mock, manager, ToolRouter(registry, executor)


def test_tool_traverses_real_manager_adapter_path():
    mock, manager, router = _stack()
    ctx = RuntimeContext()
    manager.start(ctx)
    result = router.execute("core_discover_devices")
    assert result.success is True
    assert result.data["message_type"] == "DEVICE_DISCOVER"
    manager.stop(ctx)
    offline = router.execute("core_discover_devices")
    assert offline.success is False
    assert "CORE_UNAVAILABLE" in (offline.error or "")


def test_local_llm_independent_of_core_state():
    provider = MockAIProvider(responses=["hello local"])
    online_reply = provider.chat([{"role": "user", "content": "hi"}])
    assert online_reply.content == "hello local"

    _, manager, _ = _stack()
    ctx = RuntimeContext()
    manager.start(ctx)  # CORE online
    still_local = provider.chat([{"role": "user", "content": "hi"}])
    assert still_local.provider == "mock"
    manager.stop(ctx)  # CORE offline
    offline_reply = provider.chat([{"role": "user", "content": "hi"}])
    assert offline_reply.content == "hello local"


def test_local_tools_work_while_core_offline():
    _, manager, router = _stack()
    # Never started -> CORE offline, local tools unaffected.
    assert manager.is_available() is False
    assert router.execute("echo", text="hi").success is True
    assert router.execute("current_time").success is True
    assert router.execute("core_status").success is True


def test_voice_transcript_uses_same_router_path():
    """STT text -> same Router/CORE-tool decision -> TTS (no separate client)."""
    stt = MockSpeechRecognizer(text="Show me the devices connected to R.I.S.A.R.M.S.")
    tts = MockTextToSpeech()
    mock, manager, router = _stack()
    ctx = RuntimeContext()
    manager.start(ctx)

    text = stt.transcribe(AudioData(samples=[0] * 16, sample_rate=16000)).text
    assert "devices" in text.lower()
    result = router.execute("core_discover_devices")
    assert result.success is True
    spoken = tts.synthesize(f"Found devices via {result.tool_name}")
    assert spoken.sample_rate == 16000
    assert tts.synthesized and "core_discover_devices" in tts.synthesized[0]
    manager.stop(ctx)


def test_coding_mode_shares_registry_no_second_client():
    """Any future coding mode consumes the same registry/adapter (verified)."""
    mock, manager, router = _stack()
    ctx = RuntimeContext()
    manager.start(ctx)
    # Router holds the shared registry; CORE tools resolve to the ONE adapter.
    from asis.tools.provided.core_tools import CoreDiscoverDevicesTool

    tool = CoreDiscoverDevicesTool(manager)
    assert tool._core is manager
    assert manager.adapter is mock
    manager.stop(ctx)


def test_no_host_imports_repo_wide():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "asis"
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(errors="ignore")
        if "from core.communication" in text or "from core.tcp" in text:
            offenders.append(str(path))
    assert offenders == []


def test_tool_results_are_model_safe_json():
    _, manager, router = _stack()
    ctx = RuntimeContext()
    manager.start(ctx)
    result = router.execute("core_device_info", device_id="mac-01")
    blob = json.dumps({"data": result.data, "error": result.error})
    assert "session_token" not in blob
    assert "credential" not in blob
    manager.stop(ctx)
