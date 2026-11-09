"""Tests for coding tools through the shared router/executor path."""

from __future__ import annotations

from asis.coding.tools import build_coding_registry
from asis.coding.workspace import CodingWorkspace
from asis.tools.executor import ToolExecutor
from asis.tools.router import ToolRouter


def _router(workspace: CodingWorkspace) -> ToolRouter:
    return ToolRouter(
        registry=build_coding_registry(workspace),
        executor=ToolExecutor(authorizer=lambda tool: True),
    )


def test_read_file_success(tmp_path):
    ws = CodingWorkspace(root=tmp_path.resolve())
    (tmp_path / "a.py").write_text("def f():\n    return 1\n")
    result = _router(ws).execute("read_file", path="a.py")
    assert result.success is True
    assert "return 1" in result.data["content"]


def test_read_file_missing(tmp_path):
    ws = CodingWorkspace(root=tmp_path.resolve())
    result = _router(ws).execute("read_file", path="missing.py")
    assert result.success is False
    assert "not found" in (result.error or "").lower()


def test_read_file_invalid_args(tmp_path):
    ws = CodingWorkspace(root=tmp_path.resolve())
    result = _router(ws).execute("read_file", path="")
    assert result.success is False


def test_search_files_success(tmp_path):
    ws = CodingWorkspace(root=tmp_path.resolve())
    (tmp_path / "a.py").write_text("def target_fn():\n    pass\n")
    result = _router(ws).execute("search_files", pattern="target_fn")
    assert result.success is True
    assert any(m["path"] == "a.py" for m in result.data["matches"])


def test_list_directory_success(tmp_path):
    ws = CodingWorkspace(root=tmp_path.resolve())
    (tmp_path / "sub").mkdir()
    (tmp_path / "f.py").write_text("x=1\n")
    result = _router(ws).execute("list_directory", path=".")
    assert result.success is True
    assert "f.py" in result.data["entries"]
    assert "sub/" in result.data["entries"]


def test_write_file_success(tmp_path):
    ws = CodingWorkspace(root=tmp_path.resolve())
    result = _router(ws).execute("write_file", path="new.py", content="x = 2\n")
    assert result.success is True
    assert (tmp_path / "new.py").read_text() == "x = 2\n"


def test_run_tests_structured(tmp_path):
    ws = CodingWorkspace(root=tmp_path.resolve())
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert 1 == 1\n")
    result = _router(ws).execute("run_tests", args=["test_ok.py"])
    assert result.success is True
    assert result.data["success"] is True
    assert result.data["exit_code"] == 0
    assert "command" in result.data


def test_run_tests_failure_structured(tmp_path):
    ws = CodingWorkspace(root=tmp_path.resolve())
    (tmp_path / "test_bad.py").write_text("def test_bad():\n    assert 1 == 2\n")
    result = _router(ws).execute("run_tests", args=["test_bad.py"])
    assert result.success is True  # tool ran; suite failed
    assert result.data["success"] is False
    assert result.data["exit_code"] != 0


def test_git_status_and_diff(tmp_path):
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.t"], cwd=tmp_path, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "t"], cwd=tmp_path, capture_output=True
    )
    (tmp_path / "f.txt").write_text("hi\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
    (tmp_path / "f.txt").write_text("changed\n")
    ws = CodingWorkspace(root=tmp_path.resolve())
    router = _router(ws)
    status = router.execute("git_status")
    assert status.success is True
    diff = router.execute("git_diff")
    assert diff.success is True
    assert "changed" in diff.data["diff"]


def test_unknown_tool_rejected(tmp_path):
    ws = CodingWorkspace(root=tmp_path.resolve())
    result = _router(ws).execute("nonexistent_tool")
    assert result.success is False
    assert "not found" in (result.error or "").lower()


def test_permission_denied_not_executed(tmp_path):
    ws = CodingWorkspace(root=tmp_path.resolve())
    router = ToolRouter(
        registry=build_coding_registry(ws),
        executor=ToolExecutor(authorizer=lambda tool: False),
    )
    (tmp_path / "v.py").write_text("x=1\n")
    result = router.execute("read_file", path="v.py")
    assert result.success is False
    assert "denied" in (result.error or "").lower()
