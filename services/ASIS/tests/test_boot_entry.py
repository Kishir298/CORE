"""Entry-level boot + ownership integration (no network, no real procs)."""

from __future__ import annotations

import io
from contextlib import redirect_stdout

import asis.ai.ollama_lifecycle as lifecycle
import asis.app.boot as boot_module
import asis.cli.main as main_module
from asis.ai.ollama_lifecycle import OllamaOwnership
from asis.ai.providers import MockAIProvider


class FakeProc:
    pid = 7777

    def __init__(self):
        self._alive = True
        self.terminated = 0
        self.killed = 0

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self.terminated += 1
        self._alive = False

    def kill(self):
        self.killed += 1
        self._alive = False

    def wait(self, timeout=None):
        if self._alive:
            raise TimeoutError("running")
        return 0


def test_mock_message_boots_silently(monkeypatch):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main_module.entry(["--provider", "mock", "--message", "hi"])
    out = buf.getvalue()
    assert code == 0
    assert "[ OK ] Model ready" in out
    assert "hello" not in out


def test_ollama_external_is_left_running(monkeypatch):
    stopped: list = []
    real_stop = lifecycle.stop_owned_ollama
    monkeypatch.setattr(
        lifecycle,
        "stop_owned_ollama",
        lambda o, shutdown_timeout=10: stopped.append(o) or "unowned",
    )
    monkeypatch.setattr(
        lifecycle,
        "ensure_ollama",
        lambda host, managed="auto", serve_timeout=60, **k: OllamaOwnership(
            owned=False
        ),
    )
    monkeypatch.setattr(
        main_module, "_provider", lambda name, model: MockAIProvider(model=model)
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main_module.entry(
            ["--provider", "ollama", "--model", "mock-model", "--message", "hi"]
        )
    assert code == 0
    assert len(stopped) == 1 and stopped[0].owned is False
    # Real implementation would do nothing for unowned.
    assert real_stop(OllamaOwnership(owned=False)) == "unowned"


def test_owned_ollama_cleaned_on_probe_failure(monkeypatch):
    proc = FakeProc()
    owned = OllamaOwnership(owned=True, process=proc, pid=7777)
    monkeypatch.setattr(
        lifecycle, "ensure_ollama", lambda *a, **k: owned
    )
    monkeypatch.setattr(
        main_module, "_provider", lambda name, model: MockAIProvider(model="m")
    )

    def fail_boot(*a, **k):
        raise boot_module.BootError("probe down")

    monkeypatch.setattr(boot_module, "run_boot_sequence", fail_boot)
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main_module.entry(["--provider", "ollama", "--message", "hi"])
    assert code == 1
    assert "[FAIL]" in buf.getvalue()
    assert proc.terminated == 1
    assert proc.killed == 0


def test_ollama_down_managed_off_fails_fast(monkeypatch):
    def raise_off(*a, **k):
        raise lifecycle.OllamaLifecycleError("not running and managed=off")

    monkeypatch.setattr(lifecycle, "ensure_ollama", raise_off)
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main_module.entry(["--provider", "ollama", "--message", "hi"])
    assert code == 1
    assert "Ollama unavailable" in buf.getvalue()


def test_ctrl_c_during_boot_cleans_owned_and_returns_130(monkeypatch):
    proc = FakeProc()
    owned = OllamaOwnership(owned=True, process=proc, pid=7777)
    monkeypatch.setattr(lifecycle, "ensure_ollama", lambda *a, **k: owned)
    monkeypatch.setattr(
        main_module, "_provider", lambda name, model: MockAIProvider(model="m")
    )

    def cancelled(*a, **k):
        raise KeyboardInterrupt()

    monkeypatch.setattr(boot_module, "run_boot_sequence", cancelled)
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main_module.entry(["--provider", "ollama", "--message", "hi"])
    assert code == 130
    assert proc.terminated == 1
