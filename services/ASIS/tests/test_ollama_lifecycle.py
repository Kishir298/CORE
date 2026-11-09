"""Ownership-safe Ollama lifecycle tests (no real server, no real procs)."""

from __future__ import annotations

import pytest

from asis.ai.ollama_lifecycle import (
    OllamaLifecycleError,
    OllamaOwnership,
    ensure_ollama,
    stop_owned_ollama,
)


class FakeProc:
    """Minimal Popen stand-in tracking terminate/kill only."""

    pid = 4242

    def __init__(self, exit_on_terminate: bool = True):
        self._alive = True
        self.terminated = 0
        self.killed = 0
        self.exit_on_terminate = exit_on_terminate

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self.terminated += 1
        if self.exit_on_terminate:
            self._alive = False

    def kill(self):
        self.killed += 1
        self._alive = False

    def wait(self, timeout=None):
        if self._alive:
            raise TimeoutError("still running")
        return 0


def test_already_running_never_claims_ownership():
    launched: list = []
    ownership = ensure_ollama(
        "http://127.0.0.1:11434",
        available_fn=lambda: True,
        popen_factory=lambda: launched.append(1) or FakeProc(),
        sleep=lambda s: None,
    )
    assert ownership.owned is False
    assert ownership.process is None
    assert launched == []


def test_managed_off_never_starts():
    with pytest.raises(OllamaLifecycleError):
        ensure_ollama(
            "http://127.0.0.1:11434",
            managed="off",
            available_fn=lambda: False,
            popen_factory=lambda: FakeProc(),
            sleep=lambda s: None,
        )


def test_unknown_mode_defaults_to_do_not_start():
    with pytest.raises(OllamaLifecycleError):
        ensure_ollama(
            "http://127.0.0.1:11434",
            managed="killall",
            available_fn=lambda: False,
            popen_factory=lambda: FakeProc(),
            sleep=lambda s: None,
        )


def test_starts_owned_and_records_pid():
    proc = FakeProc()
    calls = {"n": 0}

    def fake_up():
        calls["n"] += 1
        return calls["n"] > 1

    ownership = ensure_ollama(
        "http://127.0.0.1:11434",
        available_fn=fake_up,
        popen_factory=lambda bh: proc,
        sleep=lambda s: None,
    )
    assert ownership.owned is True
    assert ownership.process is proc
    assert ownership.pid == 4242


def test_early_child_exit_is_reported_and_cleaned():
    class Dead:
        pid = 1

        def poll(self):
            return 3

        def terminate(self):
            pass

    with pytest.raises(OllamaLifecycleError, match="exited early"):
        ensure_ollama(
            "http://127.0.0.1:11434",
            available_fn=lambda: False,
            popen_factory=lambda bh: Dead(),
            sleep=lambda s: None,
        )


def test_unowned_stop_never_signals():
    proc = FakeProc()
    assert stop_owned_ollama(None) == "unowned"
    assert stop_owned_ollama(OllamaOwnership(owned=False)) == "unowned"
    assert (
        stop_owned_ollama(OllamaOwnership(owned=False, process=proc, pid=1))
        == "unowned"
    )
    assert proc.terminated == 0 and proc.killed == 0


def test_owned_stop_is_graceful_and_verified():
    proc = FakeProc()
    ownership = OllamaOwnership(owned=True, process=proc, pid=4242)
    assert stop_owned_ollama(ownership, shutdown_timeout=2) == "stopped"
    assert proc.terminated == 1
    assert proc.killed == 0
    assert ownership.process is None


def test_owned_stop_escalates_only_owned_handle_when_stuck():
    proc = FakeProc(exit_on_terminate=False)
    ownership = OllamaOwnership(owned=True, process=proc, pid=4242)
    assert stop_owned_ollama(ownership, shutdown_timeout=1) == "forced"
    assert proc.terminated == 1
    assert proc.killed == 1


def test_dead_owned_handle_reports_stopped_without_signals():
    proc = FakeProc()
    proc._alive = False
    ownership = OllamaOwnership(owned=True, process=proc, pid=4242)
    assert stop_owned_ollama(ownership, shutdown_timeout=1) == "stopped"
    assert proc.terminated == 0


def test_no_broad_kill_primitives_in_lifecycle_source():
    from pathlib import Path

    text = Path("asis/ai/ollama_lifecycle.py").read_text(encoding="utf-8")
    lowered = text.lower()
    # Prose may say "never do X"; only actual command primitives are banned.
    for banned_literal in (
        '"taskkill"',
        "'taskkill'",
        '"pkill"',
        "'pkill'",
        '"killall"',
        "'killall'",
        "import psutil",
        "from psutil",
        "os.kill",
        "shell=True",
    ):
        assert banned_literal not in lowered, banned_literal
