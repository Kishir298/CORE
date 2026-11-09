"""Identity Panel - Left column box 1.

Shows A.S.I.S. title and tagline in a bordered box.
"""

from __future__ import annotations

from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static

from asis.tui.state import AppState


class IdentityPanel(Widget):
    """Left column top box: A.S.I.S. identity."""

    DEFAULT_CSS = """
    IdentityPanel {
        width: 100%;
        height: 100%;
        border: solid #30363d;
        background: #0a0e14;
    }

    IdentityPanel > Static {
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: #5ee6d0;
    }

    IdentityPanel > Static.tagline {
        text-style: dim;
        color: #6e7681;
    }
    """

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state

    def compose(self) -> Widget:
        with Vertical():
            yield Static("A.S.I.S.", id="title")
            yield Static("A Smart Intelligence System", classes="tagline", id="tagline")

    def on_mount(self) -> None:
        """Initial render."""
        self._update()

    def watch_state(self) -> None:
        """Called when state changes."""
        self._update()

    def _update(self) -> None:
        """Update display from state."""
        # Identity panel is static, no dynamic updates needed
        pass
