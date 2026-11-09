"""Integrated coding flow through the real app architecture."""

from __future__ import annotations

import subprocess

from asis.ai import AIManager
from asis.ai.models import AIResponse
from asis.ai.providers import MockAIProvider
from asis.app.assistant import AssistantApp
from asis.app.modes import AssistantMode
from asis.identity import build_identity


class ScriptedProvider(MockAIProvider):
    """Deterministic stand-in for the shared model."""

    def __init__(self, script: list[str]):
        super().__init__(responses=tuple(script))
        self.calls = 0

    def chat(self, messages):
        self.calls += 1
        response = self._next_response()
        return AIResponse(content=response, model="mock", provider="mock")


def _coding_app(memory_manager, workspace, script):
    provider = ScriptedProvider(script)
    from asis.app.assistant import build_coding_tool_router
    from asis.coding.workspace import CodingWorkspace
    from asis.tools.executor import ToolExecutor

    ws = (
        workspace
        if isinstance(workspace, CodingWorkspace)
        else CodingWorkspace(root=workspace.resolve())
    )
    router = build_coding_tool_router(
        ws, executor=ToolExecutor(authorizer=lambda tool: True)
    )
    return AssistantApp(
        identity=build_identity(),
        ai=AIManager(provider=provider),
        memory=memory_manager,
        workspace=ws,
        tools_router=router,
        mode="coding",
    )


def test_coding_request_full_path(memory_manager, tmp_path):
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    app = _coding_app(
        memory_manager,
        tmp_path,
        [
            '{"tool": "read_file", "arguments": {"path": "calc.py"}}',
            "calc.py adds two numbers.",
        ],
    )
    out = app.chat("inspect calc.py")
    assert "adds two numbers" in out
    assert any("calc.py" in m.content for m in app.session.messages)


def test_multi_turn_inspect_find_fix_diff(memory_manager, tmp_path):
    target = tmp_path / "math_ops.py"
    target.write_text("def add(a, b):\n    return a - b\n")
    (tmp_path / "test_math.py").write_text(
        "from math_ops import add\ndef test_add():\n    assert add(1, 2) == 3\n"
    )
    app = _coding_app(
        memory_manager,
        tmp_path,
        [
            '{"tool": "list_directory", "arguments": {"path": "."}}',
            "Project has math_ops.py and test_math.py.",
            '{"tool": "run_tests", "arguments": {"args": ["test_math.py"]}}',
            "test_math.py fails: add returns a - b instead of a + b.",
            (
                '{"tool": "write_file", "arguments": '
                '{"path": "math_ops.py", '
                '"content": "def add(a, b):\\n    return a + b\\n"}}'
            ),
            "Fixed add to use +.",
            '{"tool": "git_diff", "arguments": {}}',
            "Diff shows the one-line fix.",
        ],
    )
    assert "math_ops.py" in app.chat("Inspect this project.")
    assert "fails" in app.chat("Find the failing test.")
    assert "Fixed" in app.chat("Fix it.")
    assert target.read_text() == "def add(a, b):\n    return a + b\n"
    assert "Diff" in app.chat("Show me what changed.")
    assert app.mode is AssistantMode.CODING


def test_personal_memory_stays_separate_in_coding(memory_manager, tmp_path):
    app = _coding_app(memory_manager, tmp_path, ["noted"])
    app.chat("My name is Rishik.")
    assert "Rishik" in memory_manager.search_context("name")
    assert any("Rishik" in m.content for m in app.session.messages)


def test_voice_path_respects_active_mode(memory_manager, tmp_path):
    app = _coding_app(memory_manager, tmp_path, ["voice coding ok"])
    app.set_mode("coding")
    assert app.chat("hello voice") == "voice coding ok"
    assert app.mode is AssistantMode.CODING


def test_git_repo_flow_without_mutation(memory_manager, tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    (tmp_path / "f.py").write_text("x = 1\n")
    app = _coding_app(
        memory_manager,
        tmp_path,
        ['{"tool": "git_status", "arguments": {}}', "Repo has untracked f.py."],
    )
    assert "untracked" in app.chat("What is the repo state?")
