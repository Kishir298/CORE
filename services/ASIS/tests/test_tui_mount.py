"""TUI headless mount regression test."""

from __future__ import annotations

import pytest

from asis.tui.app import ASISTUI


def test_tui_headless_mount():
    """Test that TUI mounts headless without CSS errors."""
    app = ASISTUI()
    # This should not raise any CSS parsing or mount errors
    app.run(headless=True, inline=True)
    # If we get here, mount succeeded


def test_tui_headless_mount_with_mock_mode():
    """Test that TUI mounts headless in mock mode."""
    app = ASISTUI(mock_mode=True)
    app.run(headless=True, inline=True)


def test_tui_headless_mount_with_inference_options():
    """Test that TUI mounts headless with inference options."""
    app = ASISTUI(
        ai_temperature=0.5,
        ai_think="false",
        ai_num_predict=100,
        ai_keep_alive="10m",
    )
    app.run(headless=True, inline=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])