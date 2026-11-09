"""Tests for the tool subsystem: registry, provided tools and results."""

from __future__ import annotations

import pytest

from asis.errors import ToolNotFoundError, ToolValidationError
from asis.tools import ToolMetadata, ToolRegistry
from asis.tools.provided import CurrentTimeTool, EchoTool


def test_register_and_get():
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)

    assert registry.get("echo") is tool


def test_require_missing_raises():
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        registry.require("does-not-exist")


def test_duplicate_registration_raises():
    registry = ToolRegistry()
    registry.register(EchoTool())
    with pytest.raises(ToolValidationError):
        registry.register(EchoTool())


def test_register_non_tool_raises():
    registry = ToolRegistry()
    with pytest.raises(ToolValidationError):
        registry.register("not-a-tool")  # type: ignore[arg-type]


def test_echo_tool_returns_ok():
    result = EchoTool().execute(text="hello world")
    assert result.success is True
    assert result.data == {"text": "hello world"}


def test_echo_tool_fails_on_missing_text():
    result = EchoTool().execute()
    assert result.success is False


def test_current_time_tool():
    result = CurrentTimeTool().execute()
    assert result.success is True
    assert "iso" in result.data
    assert "timestamp" in result.data


def test_list_names_sorted():
    registry = ToolRegistry()
    registry.register(CurrentTimeTool())
    registry.register(EchoTool())

    assert registry.list_names() == ["current_time", "echo"]


def test_builtin_tool_metadata():
    tool = EchoTool()
    assert tool.name == "echo"
    assert tool.description
    assert tool.category == "utility"
    assert isinstance(tool.metadata, ToolMetadata)
