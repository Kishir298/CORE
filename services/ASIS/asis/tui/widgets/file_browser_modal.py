"""
File Browser Modal - In-TUI file browser for selecting files to attach.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView


class FileBrowserModal(ModalScreen[Optional[Path]]):
    """Modal file browser for selecting files to attach."""

    DEFAULT_CSS = """
    FileBrowserModal {
        align: center middle;
    }

    #file-browser-container {
        width: 80%;
        height: 80%;
        background: #111820;
        border: solid #30363d;
        padding: 1;
    }

    #file-browser-header {
        height: 3;
        background: #111820;
        border-bottom: solid #30363d;
        padding: 0 1;
    }

    #file-browser-path {
        width: 100%;
        height: 1;
        background: #111820;
        color: #c9d1d9;
        border: none;
    }

    #file-browser-list {
        width: 100%;
        height: 1fr;
        background: #111820;
        border: none;
        overflow-y: auto;
    }

    #file-browser-list > ListItem {
        height: 1;
        padding: 0 1;
        background: #111820;
    }

    #file-browser-list > ListItem:hover {
        background: #30363d;
    }

    #file-browser-list > ListItem.-highlight {
        background: #5ee6d0 30%;
        color: #c9d1d9;
    }

    .file-item {
        width: 100%;
        height: 1;
        padding: 0 1;
    }

    .file-item.directory {
        color: #61dafb;
    }

    .file-item.file {
        color: #c9d1d9;
    }

    .file-item.selected {
        background: #5ee6d0 30%;
        color: #c9d1d9;
    }

    #file-browser-footer {
        height: 3;
        background: #111820;
        border-top: solid #30363d;
        padding: 0 1;
        layout: horizontal;
    }

    #file-browser-select {
        width: 20%;
        margin-right: 1;
    }

    #file-browser-cancel {
        width: 20%;
    }

    #file-browser-up {
        width: 20%;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "select", "Select"),
        ("up", "cursor_up", "Up"),
        ("down", "cursor_down", "Down"),
        ("left", "go_up", "Parent Dir"),
        ("right", "enter_dir", "Enter Dir"),
    ]

    def __init__(self, start_path: Path | None = None) -> None:
        super().__init__()
        self.current_path = start_path or Path.home()
        self.selected_index = 0
        self._entries: list[Path] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="file-browser-container"):
            with Horizontal(id="file-browser-header"):
                yield Input(
                    value=str(self.current_path),
                    id="file-browser-path",
                    placeholder="Enter path...",
                )

            yield ListView(id="file-browser-list")

            with Horizontal(id="file-browser-footer"):
                yield Button("⬆ Up", id="file-browser-up", variant="primary")
                yield Button("Select", id="file-browser-select", variant="success")
                yield Button("Cancel", id="file-browser-cancel", variant="error")

    def on_mount(self) -> None:
        self._refresh_list()
        self.query_one("#file-browser-list", ListView).focus()

    def _refresh_list(self) -> None:
        """Refresh the file list for current directory."""
        list_view = self.query_one("#file-browser-list", ListView)
        list_view.clear()
        self._entries = []

        try:
            # Add parent directory entry
            if self.current_path.parent != self.current_path:
                self._entries.append(("..", self.current_path.parent, True))

            # List directory entries
            for entry in sorted(self.current_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                try:
                    is_dir = entry.is_dir()
                    self._entries.append((entry.name, entry, is_dir))
                except (PermissionError, OSError):
                    # Skip entries we can't access
                    pass
        except (PermissionError, OSError):
            pass

        for i, (name, path, is_dir) in enumerate(self._entries):
            prefix = "📁 " if is_dir else "📄 "
            item = ListItem(Label(f"{prefix}{name}"), id=f"file-entry-{i}")
            list_view.append(item)

        if self._entries:
            self.selected_index = min(self.selected_index, len(self._entries) - 1)
            list_view.index = self.selected_index

        # Update path input
        path_input = self.query_one("#file-browser-path", Input)
        path_input.value = str(self.current_path)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_cursor_up(self) -> None:
        list_view = self.query_one("#file-browser-list", ListView)
        if list_view.index > 0:
            list_view.index -= 1
            self.selected_index = list_view.index

    def action_cursor_down(self) -> None:
        list_view = self.query_one("#file-browser-list", ListView)
        if list_view.index < len(self._entries) - 1:
            list_view.index += 1
            self.selected_index = list_view.index

    def action_go_up(self) -> None:
        """Go to parent directory."""
        if self.current_path.parent != self.current_path:
            self.current_path = self.current_path.parent
            self.selected_index = 0
            self._refresh_list()

    def action_enter_dir(self) -> None:
        """Enter selected directory."""
        if 0 <= self.selected_index < len(self._entries):
            name, path, is_dir = self._entries[self.selected_index]
            if is_dir:
                self.current_path = path
                self.selected_index = 0
                try:
                    self._refresh_list()
                except Exception:
                    # Ignore if not mounted (e.g., in tests)
                    pass

    def action_select(self) -> None:
        """Select the current entry."""
        if 0 <= self.selected_index < len(self._entries):
            name, path, is_dir = self._entries[self.selected_index]
            if is_dir:
                self.current_path = path
                self.selected_index = 0
                try:
                    self._refresh_list()
                except Exception:
                    # Ignore if not mounted (e.g., in tests)
                    pass
            else:
                self.dismiss(path)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "file-browser-up":
            self.action_go_up()
        elif event.button.id == "file-browser-select":
            self.action_select()
        elif event.button.id == "file-browser-cancel":
            self.action_cancel()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.selected_index = event.item.id and int(event.item.id.split("-")[-1]) or 0
        self.action_select()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "file-browser-path":
            try:
                new_path = Path(event.value).expanduser().resolve()
                if new_path.exists() and new_path.is_dir():
                    self.current_path = new_path
                    self.selected_index = 0
                    self._refresh_list()
            except (ValueError, OSError):
                pass


class AttachFileScreen(ModalScreen[Optional[Path]]):
    """Screen for attaching files - shows file browser."""

    def __init__(self, start_path: Path | None = None) -> None:
        super().__init__()
        self.start_path = start_path

    def compose(self) -> ComposeResult:
        yield FileBrowserModal(self.start_path)

    def on_file_browser_modal_dismissed(self, event: FileBrowserModal.Dismissed) -> None:
        if event.result:
            self.dismiss(event.result)
