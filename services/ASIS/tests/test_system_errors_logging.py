"""Unit: errors hierarchy + logging hygiene + interrupt scopes (offline)."""

from __future__ import annotations

import logging

import pytest

from asis.errors import (
    ASISError,
    ConfigurationError,
    InferenceError,
    ModelError,
    PermissionError,
    ToolError,
    ToolNotFoundError,
    ToolValidationError,
    VoiceError,
)
from asis.system.interrupt import InterruptCoordinator


def test_error_hierarchy_mapping():
    assert issubclass(ConfigurationError, ASISError)
    assert issubclass(InferenceError, ModelError)
    assert issubclass(ToolValidationError, ToolError)
    assert issubclass(ToolNotFoundError, ToolError)
    assert issubclass(VoiceError, ASISError)
    assert issubclass(PermissionError, ASISError)
    with pytest.raises(ASISError):
        raise ToolValidationError("bad args")


def test_logging_no_duplicate_handlers_and_no_secrets():
    from asis.logging.logger import get_logger

    log1 = get_logger("gap.probe")
    log2 = get_logger("gap.probe")
    assert log1 is log2
    assert isinstance(log1, logging.Logger)
    assert len(log1.handlers) <= 2
    for handler in log1.handlers:
        assert handler.formatter is not None


def test_interrupt_scopes_register_and_cancel():
    coord = InterruptCoordinator()
    for scope in ("inference", "voice", "tools"):
        coord.register(scope)
    coord.cancel("inference")
    assert coord.is_cancelled("inference") is True
    assert coord.is_cancelled("voice") is False


def test_prompt_slice_preserves_surface():
    from asis.app import assistant, prompt, routers

    for name in (
        "build_memory_section",
        "build_mode_section",
        "build_capabilities_section",
        "build_constraints_section",
    ):
        assert callable(getattr(prompt, name))
    for name in (
        "build_default_tool_router",
        "build_coding_tool_router",
        "ensure_all_tools",
    ):
        assert callable(getattr(routers, name))
        # Backward-compat re-exports preserved on asis.app.assistant.
        assert callable(getattr(assistant, name))
    assert prompt.build_constraints_section(None) == ""
    assert "Tools:" in prompt.build_capabilities_section(["echo"])
    rtk_lines = len(open("asis/app/assistant.py").read().splitlines())
    assert rtk_lines < 600, rtk_lines
    assert prompt.build_constraints_section(None) == ""
    assert "Tools:" in prompt.build_capabilities_section(["echo"])
