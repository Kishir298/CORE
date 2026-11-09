"""Boot Log Panel - Left column box 3.

Scrollable initialization log with [BOOT]/[OK]/[FAIL] lines.
"""

from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Static

from asis.tui.state import AppState


class BootLogPanel(Widget):
    """Left column third box: scrollable boot log."""

    DEFAULT_CSS = """
    BootLogPanel {
        width: 100%;
        height: 100%;
        border: solid #30363d;
        background: #0a0e14;
    }

    BootLogPanel > VerticalScroll {
        width: 100%;
        height: 1fr;
        padding: 0 1;
    }

    BootLogPanel .log-line {
        width: 100%;
        height: 1;
        color: #c9d1d9;
    }

    BootLogPanel .log-boot {
        color: #c9d1d9;
    }

    BootLogPanel .log-ok {
        color: #3fb950;
    }

    BootLogPanel .log-fail {
        color: #f85149;
    }

    BootLogPanel .log-warn {
        color: #d29922;
    }

    BootLogPanel .caption {
        width: 100%;
        height: 1;
        content-align: center bottom;
        color: #6e7681;
        text-style: dim;
        margin-top: 1;
    }
    """

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state
        self._last_log_count = 0

    def compose(self) -> Widget:
        with VerticalScroll(id="scroll"):
            yield Static("", id="log-content")
            yield Static("A Smart Intelligence System", classes="caption", id="caption")

    def on_mount(self) -> None:
        self._update()

    def watch_state(self) -> None:
        self._update()

    def _update(self) -> None:
        log_content = self.query_one("#log-content", Static)

        if len(self.state.boot_log) == self._last_log_count:
            return

        lines = []
        for entry in self.state.boot_log:
            level_class = {
                "BOOT": "log-boot",
                "OK": "log-ok",
                "FAIL": "log-fail",
                "WARN": "log-warn",
            }.get(entry.level, "log-line")
            lines.append(f"[span.{level_class}][{entry.level}] {entry.message}[/span]")

        log_content.update("\n".join(lines))
        self._last_log_count = len(self.state.boot_log)

        # Auto-scroll to bottom
        scroll = self.query_one("#scroll", VerticalScroll)
        scroll.scroll_end(animate=False)
