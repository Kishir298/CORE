"""Boot sequence + silent readiness probe tests (no Ollama, no network)."""

from __future__ import annotations

import io

import pytest

from asis.ai.manager import AIManager
from asis.ai.models import AIMessage
from asis.ai.ollama_lifecycle import OllamaOwnership
from asis.ai.providers import MockAIProvider
from asis.app.assistant import AssistantApp
from asis.app.boot import (
    PROBE_TEXT,
    BootError,
    run_boot_sequence,
    verify_model_readiness,
)
from asis.identity import build_identity


def _memory():
    import tempfile
    from pathlib import Path

    from asis.memory import MemoryDatabase, MemoryManager, MemoryStorage

    tmp = Path(tempfile.mkdtemp()) / "boot-test.db"

    class _Mem(MemoryManager):
        pass

    return MemoryManager(MemoryStorage(MemoryDatabase(tmp)))


def _app(provider):
    identity = build_identity()
    ai = AIManager(provider=provider, event_bus=None)
    mem = _memory()
    app = AssistantApp(identity=identity, ai=ai, memory=mem)
    return identity, mem, app


def test_probe_is_single_hello_without_tools_or_history():
    seen: list = []

    class Rec(MockAIProvider):
        def chat(self, messages):
            seen.append(list(messages))
            assert len(messages) == 1
            assert messages[0].role.value == "user"
            assert messages[0].content == PROBE_TEXT
            return super().chat(messages)

    provider = Rec(model="mock", responses=("ok-response",))
    chars, _ms = verify_model_readiness(provider)
    assert chars == len("ok-response")
    assert len(seen) == 1
    # No session/history involved: probe bypasses ConversationSession.
    assert provider._index == 1


def test_probe_forces_think_false_and_restores():
    from asis.ai.providers import OllamaProvider

    captured: dict = {}
    import requests

    provider = OllamaProvider(model="qwen3:14b", think=True, num_predict=None)

    def fake_post(url, json=None, timeout=None):
        captured.update(json or {})

        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "message": {"content": "ready"},
                    "done": True,
                }

        return R()

    import unittest.mock as mock

    with mock.patch.object(requests, "post", side_effect=fake_post):
        verify_model_readiness(provider)
    assert captured.get("think") is False
    assert "tools" not in captured
    assert len(captured.get("messages", [])) == 1
    assert captured["messages"][0]["content"] == PROBE_TEXT
    # Restored after the probe (no permanent behavior change).
    assert provider.think is True
    assert provider.num_predict is None


def test_boot_sequence_reports_real_stages_and_stays_silent():
    provider = MockAIProvider(model="mock", responses=("probe-reply",))
    identity, mem, app = _app(provider)
    out = io.StringIO()
    report = run_boot_sequence(identity, mem, app, provider, out=out)
    text = out.getvalue()
    assert PROBE_TEXT not in text
    assert "probe-reply" not in text
    for label in (
        "Configuration loaded",
        "Identity loaded",
        "Personality loaded",
        "Memory initialized",
        "Tools initialized",
        "Ollama ready",
        "Model ready",
    ):
        assert label in text
    assert "A.S.I.S. ready." in text
    assert report.probe_chars == len("probe-reply")
    # Conversation isolation: nothing persisted.
    assert len(app.session.messages) == 0


def test_boot_failure_never_claims_model_ready():
    provider = MockAIProvider(model="mock", responses=("",))
    identity, mem, app = _app(provider)
    out = io.StringIO()
    with pytest.raises(BootError):
        run_boot_sequence(identity, mem, app, provider, out=out)
    text = out.getvalue()
    assert "[FAIL] Model readiness check failed" in text
    assert "[ OK ] Model ready" not in text
    assert len(app.session.messages) == 0


def test_boot_failure_from_transport_is_silent_about_probe():
    class Down(MockAIProvider):
        def chat(self, messages: list[AIMessage]):  # type: ignore[override]
            raise ConnectionError("ollama down")

        def available(self, timeout=None):
            return True

    provider = Down(model="mock")
    identity, mem, app = _app(provider)
    out = io.StringIO()
    with pytest.raises(BootError):
        run_boot_sequence(identity, mem, app, provider, out=out)
    assert "[ OK ] Model ready" not in out.getvalue()


def test_probe_does_not_touch_memory_or_history():
    provider = MockAIProvider(model="mock", responses=("hi there",))
    identity, mem, app = _app(provider)
    before = list(app.session.messages)
    out = io.StringIO()
    run_boot_sequence(identity, mem, app, provider, out=out)
    assert list(app.session.messages) == before == []
    assert PROBE_TEXT not in out.getvalue()


def test_ownership_flag_flows_into_report():
    provider = MockAIProvider(model="mock", responses=("ok",))
    identity, mem, app = _app(provider)
    out = io.StringIO()
    report = run_boot_sequence(
        identity, mem, app, provider, OllamaOwnership(owned=True), out=out
    )
    assert report.ollama_owned is True
