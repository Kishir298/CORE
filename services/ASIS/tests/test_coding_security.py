"""Security tests: workspace boundary, allowlist, timeouts, git safety."""

from __future__ import annotations

import subprocess

import pytest

from asis.coding.tools import build_coding_registry
from asis.coding.workspace import CodingWorkspace
from asis.permissions.sandbox import SandboxViolation
from asis.tools.executor import ToolExecutor
from asis.tools.router import ToolRouter


def _router(workspace: CodingWorkspace, **kwargs) -> ToolRouter:
    return ToolRouter(
        registry=build_coding_registry(workspace),
        executor=ToolExecutor(authorizer=lambda tool: True, **kwargs),
    )


def test_traversal_blocked(tmp_path):
    ws = CodingWorkspace(root=tmp_path.resolve())
    with pytest.raises(SandboxViolation):
        ws.resolve("../../etc/passwd")
    result = _router(ws).execute("read_file", path="../../etc/passwd")
    assert result.success is False


def test_absolute_outside_blocked(tmp_path):
    ws = CodingWorkspace(root=tmp_path.resolve())
    result = _router(ws).execute("read_file", path="/etc/passwd")
    assert result.success is False


def test_symlink_escape_blocked(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret\n")
    link = tmp_path / "ws" / "evil"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    ws = CodingWorkspace(root=(tmp_path / "ws").resolve())
    result = _router(ws).execute("read_file", path="evil")
    assert result.success is False


def test_write_outside_blocked(tmp_path):
    ws = CodingWorkspace(root=tmp_path.resolve())
    result = _router(ws).execute("write_file", path="../../tmp/evil.txt", content="x")
    assert result.success is False
    assert not (tmp_path.parent / "evil.txt").exists()


def test_disallowed_command_blocked(tmp_path):
    ws = CodingWorkspace(root=tmp_path.resolve())
    result = _router(ws).execute("run_command", argv=["rm", "-rf", "/"])
    assert result.success is False
    assert "not allowed" in (result.error or "")


def test_shell_string_rejected(tmp_path):
    ws = CodingWorkspace(root=tmp_path.resolve())
    result = _router(ws).execute("run_command", argv="pytest -q")
    assert result.success is False


def test_command_timeout(tmp_path):
    ws = CodingWorkspace(root=tmp_path.resolve())
    (tmp_path / "test_slow.py").write_text(
        "import time\ndef test_slow():\n    time.sleep(30)\n"
    )
    from asis.tools.executor import ToolExecutor as Ex

    tool = build_coding_registry(ws).get("run_tests")
    assert tool is not None
    executor = Ex(authorizer=lambda t: True, timeout=0.3)
    result = executor.execute(tool, args=["test_slow.py"])
    assert result.success is False
    assert "timed out" in (result.error or "").lower()


def test_unauthorized_write_blocked(tmp_path):
    ws = CodingWorkspace(root=tmp_path.resolve())
    router = ToolRouter(
        registry=build_coding_registry(ws),
        executor=ToolExecutor(authorizer=lambda tool: False),
    )
    result = router.execute("write_file", path="x.py", content="y")
    assert result.success is False
    assert not (tmp_path / "x.py").exists()


def test_unauthorized_git_blocked(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    ws = CodingWorkspace(root=tmp_path.resolve())
    router = ToolRouter(
        registry=build_coding_registry(ws),
        executor=ToolExecutor(authorizer=lambda tool: False),
    )
    result = router.execute("git_commit", message="sneaky")
    assert result.success is False


def test_git_diff_flag_injection_blocked(tmp_path):
    ws = CodingWorkspace(root=tmp_path.resolve())
    result = _router(ws).execute("git_diff", args=["--no-pager", "--output=/tmp/x"])
    assert result.success is False
