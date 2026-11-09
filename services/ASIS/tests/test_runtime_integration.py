"""CLI-level integration: multi-turn, memory-aware and tool paths."""

from __future__ import annotations

from asis.cli import entry


def test_cli_multi_turn_repl_shares_session(tmp_path, capsys, monkeypatch):
    import io

    db = str(tmp_path / "cli.db")
    monkeypatch.setattr(
        "sys.stdin", io.StringIO("hello\nsecond message\nasis shutdown\n")
    )
    code = entry(["--provider", "mock", "--memory-db", db])
    out = capsys.readouterr().out
    assert code == 0
    assert "[Enter] Send" in out  # footer goodbye panel
    # Two assistant replies (mock default response) + greeting.
    assert out.count("mock response") >= 2


def test_cli_message_memory_aware_path(tmp_path, capsys):
    db = str(tmp_path / "mem.db")
    assert (
        entry(
            ["--provider", "mock", "--message", "My name is Rishik.", "--memory-db", db]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        entry(["--provider", "mock", "--message", "hello again", "--memory-db", db])
        == 0
    )
    out = capsys.readouterr().out
    assert out.strip()


def test_cli_tool_execution_path(tmp_path, capsys, monkeypatch):
    from asis.ai.providers import MockAIProvider
    from asis.cli import main as cli_main

    db = str(tmp_path / "tool.db")
    responses = iter(
        ['{"tool": "echo", "arguments": {"text": "hi"}}', "echo wrapped done"]
    )

    class SeqMock(MockAIProvider):
        def chat(self, messages):
            from asis.ai.models import AIResponse

            return AIResponse(content=next(responses), model="mock", provider="mock")

    monkeypatch.setattr(cli_main, "_provider", lambda *a, **k: SeqMock())
    code = entry(
        ["--provider", "mock", "--message", "please echo hi", "--memory-db", db]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "echo wrapped done" in out


def test_cli_existing_flags_still_compatible(capsys, tmp_path):
    assert entry(["--version"]) == 0
    capsys.readouterr()
    assert entry(["--identify"]) == 0
    capsys.readouterr()
    assert entry(["--list-tools"]) == 0
    out = capsys.readouterr().out
    assert "echo" in out and "current_time" in out


def test_voice_process_fn_uses_shared_assistant_path():
    import tempfile
    from pathlib import Path

    from asis.ai import AIManager
    from asis.ai.providers import MockAIProvider
    from asis.app.assistant import AssistantApp
    from asis.identity import build_identity
    from asis.memory import MemoryDatabase, MemoryManager, MemoryStorage

    with tempfile.TemporaryDirectory() as tmp:
        memory = MemoryManager(MemoryStorage(MemoryDatabase(Path(tmp) / "v.db")))
        app = AssistantApp(
            identity=build_identity(),
            ai=AIManager(provider=MockAIProvider(responses=("voice ok",))),
            memory=memory,
        )
        # Same callable shape as cli/voice.py process_fn.
        assert app.chat("hello voice") == "voice ok"
        assert len(app.session.messages) == 2
