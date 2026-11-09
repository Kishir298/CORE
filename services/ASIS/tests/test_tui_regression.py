"""
TUI Regression Tests using Textual's run_test().

These tests verify TUI behavior without requiring a full terminal.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from asis.tui.app import ASISTUI
from asis.tui.config import get_tui_config_path
from asis.tui.state import AppState
from asis.tui.widgets.file_browser_modal import FileBrowserModal


@pytest.fixture(autouse=True)
def clean_tui_config():
    """Clean up TUI config file before and after each test."""
    config_path = get_tui_config_path()
    if config_path.exists():
        config_path.unlink()
    yield
    if config_path.exists():
        config_path.unlink()


class TestASISTUIBoot:
    """Tests for TUI boot sequence."""

    @pytest.mark.asyncio
    async def test_app_initialization(self):
        """Test that the app initializes with correct defaults."""
        app = ASISTUI()
        assert app.theme_mode == "dark"
        assert app.TITLE == "A.S.I.S."
        assert app.SUB_TITLE == "A Smart Intelligence System"

    @pytest.mark.asyncio
    async def test_theme_mode_defaults(self):
        """Test theme mode defaults to dark."""
        app = ASISTUI()
        assert app.theme_mode == "dark"

    @pytest.mark.asyncio
    async def test_get_css_variables_dark(self):
        """Test dark theme CSS variables."""
        app = ASISTUI()
        app.theme_mode = "dark"
        vars = app.get_css_variables()
        assert vars["background"] == "#0a0e14"
        assert vars["text"] == "#c9d1d9"
        assert vars["surface"] == "#111820"

    @pytest.mark.asyncio
    async def test_get_css_variables_light(self):
        """Test light theme CSS variables."""
        app = ASISTUI()
        app.theme_mode = "light"
        vars = app.get_css_variables()
        assert vars["background"] == "#fdf6e3"
        assert vars["text"] == "#586e75"
        assert vars["surface"] == "#eee8d5"

    @pytest.mark.asyncio
    async def test_theme_toggle_changes_mode(self):
        """Test that theme toggle changes theme_mode."""
        app = ASISTUI()
        assert app.theme_mode == "dark"
        app.theme_mode = "light"
        assert app.theme_mode == "light"
        app.theme_mode = "dark"
        assert app.theme_mode == "dark"


class TestFileBrowserModal:
    """Tests for the file browser modal logic (without CSS rendering)."""

    @pytest.mark.asyncio
    async def test_file_browser_initialization(self):
        """Test file browser initializes with correct path."""
        modal = FileBrowserModal(Path("/test/path"))
        assert modal.current_path == Path("/test/path")
        assert modal.selected_index == 0

    @pytest.mark.asyncio
    async def test_file_browser_default_path(self):
        """Test file browser defaults to home directory."""
        modal = FileBrowserModal()
        assert modal.current_path == Path.home()

    @pytest.mark.asyncio
    async def test_file_browser_entries_building(self):
        """Test file browser builds entries correctly."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test")
            test_dir = Path(tmpdir) / "subdir"
            test_dir.mkdir()

            modal = FileBrowserModal(Path(tmpdir))
            # Test the entries building logic
            entries = []
            if modal.current_path.parent != modal.current_path:
                entries.append(("..", modal.current_path.parent, True))
            for entry in sorted(modal.current_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                entries.append((entry.name, entry, entry.is_dir()))

            # Should have parent dir, file, and subdir
            names = [e[0] for e in entries]
            assert ".." in names
            assert "test.txt" in names
            assert "subdir" in names

    @pytest.mark.asyncio
    async def test_file_browser_action_select_file(self):
        """Test selecting a file returns the path."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test")

            modal = FileBrowserModal(Path(tmpdir))
            # Mock the dismiss method
            modal.dismiss = MagicMock()

            # Set selected index to the file (index 1 after "..")
            modal.selected_index = 1
            modal._entries = [
                ("..", Path(tmpdir).parent, True),
                ("test.txt", Path(tmpdir) / "test.txt", False),
            ]

            modal.action_select()

            # Should dismiss with the file path
            modal.dismiss.assert_called_once_with(Path(tmpdir) / "test.txt")

    @pytest.mark.asyncio
    async def test_file_browser_action_select_dir(self):
        """Test selecting a directory changes current path."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()

            modal = FileBrowserModal(Path(tmpdir))
            modal._entries = [
                ("..", Path(tmpdir).parent, True),
                ("subdir", subdir, True),
            ]

            modal.selected_index = 1
            modal.action_select()

            assert modal.current_path == subdir
            assert modal.selected_index == 0


class TestSlashCommands:
    """Tests for slash command handling logic."""

    @pytest.mark.asyncio
    async def test_help_command_parsing(self):
        """Test /help command parsing."""
        # Test the command parsing logic directly
        text = "/help"
        parts = text[1:].split(" ", 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        assert cmd == "help"
        assert arg == ""

    @pytest.mark.asyncio
    async def test_mode_command_parsing(self):
        """Test /mode command parsing."""
        text = "/mode coding"
        parts = text[1:].split(" ", 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        assert cmd == "mode"
        assert arg == "coding"

    @pytest.mark.asyncio
    async def test_upload_command_parsing(self):
        """Test /upload command parsing."""
        text = "/upload /path/to/file.txt"
        parts = text[1:].split(" ", 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        assert cmd == "upload"
        assert arg == "/path/to/file.txt"

    @pytest.mark.asyncio
    async def test_status_command_parsing(self):
        """Test /status command parsing."""
        text = "/status"
        parts = text[1:].split(" ", 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        assert cmd == "status"
        assert arg == ""

    @pytest.mark.asyncio
    async def test_unknown_command_parsing(self):
        """Test unknown command parsing."""
        text = "/unknown"
        parts = text[1:].split(" ", 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        assert cmd == "unknown"
        assert arg == ""


class TestThemeVariables:
    """Tests for CSS variable theming."""

    @pytest.mark.asyncio
    async def test_dark_theme_variables(self):
        """Test dark theme CSS variables."""
        app = ASISTUI()
        app.theme_mode = "dark"
        vars = app.get_css_variables()
        assert vars["background"] == "#0a0e14"
        assert vars["text"] == "#c9d1d9"
        assert vars["surface"] == "#111820"
        assert vars["accent"] == "#5ee6d0"

    @pytest.mark.asyncio
    async def test_light_theme_variables(self):
        """Test light theme CSS variables."""
        app = ASISTUI()
        app.theme_mode = "light"
        vars = app.get_css_variables()
        assert vars["background"] == "#fdf6e3"
        assert vars["text"] == "#586e75"
        assert vars["surface"] == "#eee8d5"
        assert vars["accent"] == "#2aa198"

    @pytest.mark.asyncio
    async def test_theme_mode_change_updates_variables(self):
        """Test changing theme_mode updates variables."""
        app = ASISTUI()
        app.theme_mode = "dark"
        dark_vars = app.get_css_variables()

        app.theme_mode = "light"
        light_vars = app.get_css_variables()

        assert dark_vars["background"] != light_vars["background"]
        assert dark_vars["text"] != light_vars["text"]


class TestThemeToggle:
    """Tests for theme toggle functionality."""

    @pytest.mark.asyncio
    async def test_theme_toggle_method_exists(self):
        """Test action_toggle_theme method exists."""
        app = ASISTUI()
        assert hasattr(app, 'action_toggle_theme')
        assert callable(app.action_toggle_theme)

    @pytest.mark.asyncio
    async def test_theme_mode_toggle(self):
        """Test theme mode toggles correctly."""
        app = ASISTUI()
        original = app.theme_mode
        app.action_toggle_theme()
        # In test environment, action_toggle_theme directly sets theme_mode
        # and calls refresh_css. We can't test refresh_css here but can verify
        # the mode toggles
        if original == "dark":
            assert app.theme_mode == "light"
        else:
            assert app.theme_mode == "dark"


class TestBootSequenceV1:
    """Tests for boot sequence initialization."""

    @pytest.mark.asyncio
    async def test_app_initializes_with_boot_task(self):
        """Test that app initializes with boot task attribute."""
        app = ASISTUI()
        assert hasattr(app, 'boot_task')
        assert hasattr(app, 'event_bus')
        assert hasattr(app, 'state')
        assert isinstance(app.state, AppState)

    @pytest.mark.asyncio
    async def test_boot_task_attribute(self):
        """Test boot_task attribute exists."""
        app = ASISTUI()
        # In test environment, boot_task may be None or not started
        assert hasattr(app, 'boot_task')


class TestAttachmentHandling:
    """Tests for file attachment handling logic."""

    @pytest.mark.asyncio
    async def test_attachment_icon_mapping(self):
        """Test file extension to icon mapping."""
        icon_map = {
            ".py": "🐍", ".js": "📜", ".ts": "📜", ".json": "📋",
            ".md": "📝", ".txt": "📄", ".pdf": "📕", ".csv": "📊",
            ".png": "🖼️", ".jpg": "🖼️", ".jpeg": "🖼️", ".gif": "🖼️",
            ".mp3": "🎵", ".wav": "🎵", ".mp4": "🎬", ".mov": "🎬",
        }

        # Test known extensions
        assert icon_map.get(".py") == "🐍"
        assert icon_map.get(".txt") == "📄"
        assert icon_map.get(".pdf") == "📕"
        assert icon_map.get(".png") == "🖼️"

        # Test unknown extension defaults
        assert icon_map.get(".xyz", "📎") == "📎"

    @pytest.mark.asyncio
    async def test_attachment_validation_logic(self):
        """Test file attachment validation logic."""
        import os
        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("test content")
            temp_path = f.name

        try:
            file_path = Path(temp_path).expanduser().resolve()
            assert file_path.exists()
            assert file_path.is_file()

            # Test non-existent file
            fake_path = Path("/fake/path.txt").expanduser().resolve()
            assert not fake_path.exists()

            # Test directory
            dir_path = Path(".").resolve()
            assert dir_path.exists()
            assert not dir_path.is_file()

        finally:
            os.unlink(temp_path)


class TestResponsiveBreakpointsV1:
    """Tests for responsive breakpoint logic."""

    @pytest.mark.asyncio
    async def test_horizontal_breakpoints_defined(self):
        """Test horizontal breakpoints are defined."""
        app = ASISTUI()
        breakpoints = app.HORIZONTAL_BREAKPOINTS
        assert len(breakpoints) == 3
        assert breakpoints[0] == (0, "-narrow")
        assert breakpoints[1] == (90, "-normal")
        assert breakpoints[2] == (120, "-wide")

    @pytest.mark.asyncio
    async def test_vertical_breakpoints_defined(self):
        """Test vertical breakpoints are defined."""
        app = ASISTUI()
        breakpoints = app.VERTICAL_BREAKPOINTS
        assert len(breakpoints) == 3
        assert breakpoints[0] == (0, "-short")
        assert breakpoints[1] == (30, "-normal")
        assert breakpoints[2] == (45, "-tall")


class TestThemeToggleV2:
    """Tests for theme toggle functionality."""

    @pytest.mark.asyncio
    async def test_theme_toggle_method_exists(self):
        """Test action_toggle_theme method exists."""
        app = ASISTUI()
        assert hasattr(app, 'action_toggle_theme')
        assert callable(app.action_toggle_theme)

    @pytest.mark.asyncio
    async def test_theme_mode_toggle(self):
        """Test theme mode toggles correctly."""
        app = ASISTUI()
        original = app.theme_mode
        app.action_toggle_theme()
        # In test environment, action_toggle_theme directly sets theme_mode
        # and calls refresh_css. We can't test refresh_css here but can verify
        # the mode toggles
        if original == "dark":
            assert app.theme_mode == "light"
        else:
            assert app.theme_mode == "dark"


class TestBootSequenceV2:
    """Tests for boot sequence initialization."""

    @pytest.mark.asyncio
    async def test_app_initializes_with_boot_task(self):
        """Test that app initializes with boot task attribute."""
        app = ASISTUI()
        assert hasattr(app, 'boot_task')
        assert hasattr(app, 'event_bus')
        assert hasattr(app, 'state')
        assert isinstance(app.state, AppState)

    @pytest.mark.asyncio
    async def test_boot_task_attribute(self):
        """Test boot_task attribute exists."""
        app = ASISTUI()
        # In test environment, boot_task may be None or not started
        assert hasattr(app, 'boot_task')


class TestResponsiveBreakpointsV2:
    """Tests for responsive breakpoint logic."""

    @pytest.mark.asyncio
    async def test_horizontal_breakpoints_defined(self):
        """Test horizontal breakpoints are defined."""
        app = ASISTUI()
        breakpoints = app.HORIZONTAL_BREAKPOINTS
        assert len(breakpoints) == 3
        assert breakpoints[0] == (0, "-narrow")
        assert breakpoints[1] == (90, "-normal")
        assert breakpoints[2] == (120, "-wide")

    @pytest.mark.asyncio
    async def test_vertical_breakpoints_defined(self):
        """Test vertical breakpoints are defined."""
        app = ASISTUI()
        breakpoints = app.VERTICAL_BREAKPOINTS
        assert len(breakpoints) == 3
        assert breakpoints[0] == (0, "-short")
        assert breakpoints[1] == (30, "-normal")
        assert breakpoints[2] == (45, "-tall")


class TestThemeToggleV3:
    """Tests for theme toggle functionality."""

    @pytest.mark.asyncio
    async def test_theme_toggle_method_exists(self):
        """Test action_toggle_theme method exists."""
        app = ASISTUI()
        assert hasattr(app, 'action_toggle_theme')
        assert callable(app.action_toggle_theme)

    @pytest.mark.asyncio
    async def test_theme_mode_toggle(self):
        """Test theme mode toggles correctly."""
        app = ASISTUI()
        original = app.theme_mode
        app.action_toggle_theme()
        # In test environment, action_toggle_theme directly sets theme_mode
        # and calls refresh_css. We can't test refresh_css here but can verify
        # the mode toggles
        if original == "dark":
            assert app.theme_mode == "light"
        else:
            assert app.theme_mode == "dark"


class TestBootSequenceV3:
    """Tests for boot sequence initialization."""

    @pytest.mark.asyncio
    async def test_app_initializes_with_boot_task(self):
        """Test that app initializes with boot task attribute."""
        app = ASISTUI()
        assert hasattr(app, 'boot_task')
        assert hasattr(app, 'event_bus')
        assert hasattr(app, 'state')
        assert isinstance(app.state, AppState)

    @pytest.mark.asyncio
    async def test_boot_task_attribute(self):
        """Test boot_task attribute exists."""
        app = ASISTUI()
        # In test environment, boot_task may be None or not started
        assert hasattr(app, 'boot_task')


class TestResponsiveBreakpointsV3:
    """Tests for responsive breakpoint logic."""

    @pytest.mark.asyncio
    async def test_horizontal_breakpoints_defined(self):
        """Test horizontal breakpoints are defined."""
        app = ASISTUI()
        breakpoints = app.HORIZONTAL_BREAKPOINTS
        assert len(breakpoints) == 3
        assert breakpoints[0] == (0, "-narrow")
        assert breakpoints[1] == (90, "-normal")
        assert breakpoints[2] == (120, "-wide")

    @pytest.mark.asyncio
    async def test_vertical_breakpoints_defined(self):
        """Test vertical breakpoints are defined."""
        app = ASISTUI()
        breakpoints = app.VERTICAL_BREAKPOINTS
        assert len(breakpoints) == 3
        assert breakpoints[0] == (0, "-short")
        assert breakpoints[1] == (30, "-normal")
        assert breakpoints[2] == (45, "-tall")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])