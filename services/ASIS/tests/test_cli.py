"""Tests for the command-line interface entry point."""

from __future__ import annotations

from asis.ai import AIManager
from asis.ai.providers import MockAIProvider
from asis.cli import build_memory, build_parser, entry, handle_message
from asis.identity import build_identity


def test_version_flag(capsys):
    code = entry(["--version"])
    out = capsys.readouterr().out

    assert code == 0
    assert "A.S.I.S." in out
    assert "0.1.0" in out


def test_identify_flag(capsys):
    code = entry(["--identify"])
    out = capsys.readouterr().out

    assert code == 0
    assert "You are" in out


def test_list_tools(capsys):
    code = entry(["--list-tools"])
    out = capsys.readouterr().out

    assert code == 0
    assert "echo" in out
    assert "current_time" in out
    assert "core_discover_devices" in out
    assert "core_data_request" in out
    assert "core_send_to_device" in out


def test_core_status_flag(capsys):
    code = entry(["--core-status"])
    out = capsys.readouterr().out

    assert code == 0
    assert "CORE:" in out
    assert "token" not in out.lower()


def test_message_flag_with_mock_provider(tmp_path, capsys):
    db = str(tmp_path / "memory.db")
    code = entry(["--provider", "mock", "--message", "Hello there!", "--memory-db", db])
    out = capsys.readouterr().out

    assert code == 0
    assert out.strip()


def test_handle_message_returns_assistant_text(memory_manager):
    identity = build_identity()
    ai = AIManager(provider=MockAIProvider(responses=("Mock says hi.",)))

    text = handle_message(identity, ai, memory_manager, "Hi")

    assert text == "Mock says hi."


def test_build_parser_defaults():
    args = build_parser().parse_args(["--provider", "mock"])
    assert args.provider == "mock"


def test_build_memory_uses_given_storage(tmp_path):
    manager = build_memory(tmp_path / "mem.db")
    assert manager is not None


def test_preview_flag_renders_layout(capsys):
    code = entry(["--preview"])
    out = capsys.readouterr().out

    assert code == 0
    # Header
    assert "A.S.I.S." in out
    assert "A Smart Intelligence System" in out
    assert "● ONLINE" in out
    # Status panel
    assert "MODEL:" in out
    assert "OLLAMA:" in out
    assert "MEMORY:" in out
    assert "TOOLS:" in out
    assert "VOICE:" in out
    # Composer
    assert "MODE:" in out
    assert "[+] Attach" in out
    assert "[Enter] Send" in out
    assert "[Esc] Cancel" in out
    # Bottom strip
    assert "TEXT MODE" in out
    assert "OLLAMA ●" in out
    assert "MEMORY ●" in out
    assert "TOOLS ●" in out
    assert "VOICE ●" in out
    # Footer
    assert "[Ctrl+C] Exit" in out
