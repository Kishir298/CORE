"""Header Bar - Right column top.

Shows MODE: GENERAL/CODING and workspace path when active.
"""

from __future__ import annotations

from textual.widget import Widget
from textual.widgets import Static

from asis.tui.state import AppState, AssistantMode


class HeaderBar(Widget):
    """Right column header: mode indicator + workspace."""

    DEFAULT_CSS = """
    HeaderBar {
        width: 100%;
        height: 100%;
        border: solid #30363d;
        background: #0a0e14;
        padding: 0 1;
    }

    HeaderBar > Static {
        width: 100%;
        height: 1;
        content-align: left middle;
    }

    HeaderBar .mode-label {
        color: #5ee6d0;
        text-style: bold;
    }

    HeaderBar .workspace-path {
        color: #6e7681;
        text-style: dim;
    }
    """

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state

    def compose(self) -> Widget:
        yield Static("", id="header-content")

    def on_mount(self) -> None:
        self._update()

    def watch_state(self) -> None:
        self._update()

    def _update(self) -> None:
        header = self.query_one("#header-content", Static)

        mode_text = self.state.assistant_mode.value
        content = f"[mode-label]MODE: {mode_text}[/mode-label]"

        if self.state.assistant_mode == AssistantMode.CODING and self.state.workspace_path:
            content += f"  [workspace-path]{self.state.workspace_path}[/workspace-path]"

        header.update(content)
