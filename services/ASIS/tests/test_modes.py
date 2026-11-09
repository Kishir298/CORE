"""Tests for the GENERAL/CODING mode system (shared provider/model)."""

from __future__ import annotations

import pytest

from asis.ai import AIManager
from asis.ai.providers import MockAIProvider
from asis.app.assistant import AssistantApp
from asis.app.modes import AssistantMode, parse_mode
from asis.app.profiles import get_profile, list_modes
from asis.identity import build_identity


def _app(memory_manager, workspace, responses=("ok",), **kwargs):
    return AssistantApp(
        identity=build_identity(),
        ai=AIManager(provider=MockAIProvider(responses=responses)),
        memory=memory_manager,
        workspace=workspace,
        **kwargs,
    )


def test_parse_mode_case_insensitive():
    assert parse_mode("GENERAL") is AssistantMode.GENERAL
    assert parse_mode(" Coding ") is AssistantMode.CODING


def test_parse_mode_invalid():
    with pytest.raises(ValueError):
        parse_mode("research")


def test_list_modes_general_first():
    assert list_modes() == [
        AssistantMode.GENERAL,
        AssistantMode.CODING,
        AssistantMode.TRANSLATION,
    ]


def test_profiles_centralized():
    general = get_profile(AssistantMode.GENERAL)
    coding = get_profile(AssistantMode.CODING)
    assert (
        "coding" not in general.instructions.lower()
        or "coding help" in general.instructions.lower()
    )
    assert "A.S.C.S." in coding.instructions
    assert "workspace" in coding.instructions.lower()


def test_default_mode_is_general(memory_manager, tmp_path):
    app = _app(memory_manager, tmp_path)
    assert app.mode is AssistantMode.GENERAL


def test_switch_general_coding_general(memory_manager, tmp_path):
    app = _app(memory_manager, tmp_path)
    assert app.set_mode("coding") is AssistantMode.CODING
    assert app.mode is AssistantMode.CODING
    assert app.set_mode(AssistantMode.GENERAL) is AssistantMode.GENERAL


def test_invalid_mode_switch_rejected(memory_manager, tmp_path):
    app = _app(memory_manager, tmp_path)
    with pytest.raises(ValueError):
        app.set_mode("research")
    assert app.mode is AssistantMode.GENERAL


def test_mode_persists_within_session(memory_manager, tmp_path):
    app = _app(memory_manager, tmp_path, responses=("one", "two"))
    app.set_mode("coding")
    app.chat("inspect this project")
    assert app.mode is AssistantMode.CODING
    assert len(app.session.messages) >= 2


def test_shared_provider_across_mode_switches(memory_manager, tmp_path):
    provider = MockAIProvider(responses=("r1", "r2", "r3"))
    app = AssistantApp(
        identity=build_identity(),
        ai=AIManager(provider=provider),
        memory=memory_manager,
        workspace=tmp_path,
    )
    first = app.ai.provider
    app.chat("hello")
    app.set_mode("coding")
    assert app.ai.provider is first
    app.chat("inspect this project")
    app.set_mode("general")
    assert app.ai.provider is first
    assert app.ai.provider.model == first.model


def test_coding_router_has_coding_tools(memory_manager, tmp_path):
    app = _app(memory_manager, tmp_path)
    assert "read_file" not in app.tools_router.registry.list_names()
    app.set_mode("coding")
    names = app.tools_router.registry.list_names()
    for expected in (
        "read_file",
        "search_files",
        "list_directory",
        "write_file",
        "run_tests",
        "git_status",
        "git_diff",
    ):
        assert expected in names


def test_general_mode_no_repo_injection(memory_manager, tmp_path):
    seen: dict = {}

    class Capturing(MockAIProvider):
        def chat(self, messages):
            seen["system"] = messages[0].content
            from asis.ai.models import AIResponse

            return AIResponse(content="ok", model="m", provider="mock")

    app = AssistantApp(
        identity=build_identity(),
        ai=AIManager(provider=Capturing()),
        memory=memory_manager,
        workspace=tmp_path,
    )
    app.chat("hello")
    assert "REPOSITORY CONTEXT" not in seen["system"]
    assert "A.S.C.S." not in seen["system"]


def test_coding_mode_injects_profile_and_repo(memory_manager, tmp_path):
    seen: dict = {}

    class Capturing(MockAIProvider):
        def chat(self, messages):
            seen["system"] = messages[0].content
            from asis.ai.models import AIResponse

            return AIResponse(content="ok", model="m", provider="mock")

    (tmp_path / "main.py").write_text("x = 1\n")
    app = AssistantApp(
        identity=build_identity(),
        ai=AIManager(provider=Capturing()),
        memory=memory_manager,
        workspace=tmp_path,
        mode="coding",
    )
    app.chat("inspect this project")
    assert "A.S.C.S." in seen["system"]
    assert "REPOSITORY CONTEXT" in seen["system"]
    assert "main.py" in seen["system"]


def test_cli_mode_commands(tmp_path, memory_manager):
    from asis.cli import handle_mode_command

    app = _app(memory_manager, tmp_path)
    assert "general" in handle_mode_command(app, "/mode")
    assert "coding mode" in handle_mode_command(app, "/ascs").lower()
    assert app.mode is AssistantMode.CODING
    assert "general" in handle_mode_command(app, "/mode general").lower()
    assert "coding" in handle_mode_command(app, "/mode coding").lower()
    assert "Unknown assistant mode" in handle_mode_command(app, "/mode nope")
    assert handle_mode_command(app, "hello") is None
