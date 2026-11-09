"""Mode Footer Panel - Left column box 4.

Condensed boot recap + mode toggle control [ TEXT ] [ VOICE ].
"""

from __future__ import annotations

from textual.containers import VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Static

from asis.tui.state import AppState, InteractionMode


class ModeFooterPanel(Widget):
    """Left column bottom box: mode toggle + condensed boot log."""

    DEFAULT_CSS = """
    ModeFooterPanel {
        width: 100%;
        height: 100%;
        border: solid #30363d;
        background: #0a0e14;
        padding: 0 1;
    }

    ModeFooterPanel > VerticalScroll {
        width: 100%;
        height: 1fr;
        padding: 0;
    }

    ModeFooterPanel .recap-line {
        width: 100%;
        height: 1;
        color: #6e7681;
        text-style: dim;
    }

    ModeFooterPanel .mode-toggle {
        width: 100%;
        height: 3;
        margin-top: 1;
    }

    ModeFooterPanel .mode-btn {
        width: 50%;
        min-width: 0;
    }

    ModeFooterPanel .mode-btn-active {
        background: #5ee6d0;
        color: #0a0e14;
        text-style: bold;
    }

    ModeFooterPanel .mode-btn-inactive {
        background: #111820;
        color: #6e7681;
        border: solid #30363d;
    }
    """

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state

    def compose(self) -> Widget:
        with VerticalScroll(id="scroll"):
            yield Static("", id="recap")
            with Button("TEXT", id="btn-text", classes="mode-btn"):
                pass
            with Button("VOICE", id="btn-voice", classes="mode-btn"):
                pass

    def on_mount(self) -> None:
        self._update()
        self._update_buttons()

    def watch_state(self) -> None:
        self._update()
        self._update_buttons()

    def _update(self) -> None:
        recap = self.query_one("#recap", Static)

        # Show condensed boot events (last few)
        lines = []
        for entry in self.state.boot_log[-6:]:
            level_class = {
                "BOOT": "log-boot",
                "OK": "log-ok",
                "FAIL": "log-fail",
                "WARN": "log-warn",
            }.get(entry.level, "recap-line")
            lines.append(f"[span.{level_class}][{entry.level}] {entry.message}[/span]")

        recap.update("\n".join(lines))

    def _update_buttons(self) -> None:
        btn_text = self.query_one("#btn-text", Button)
        btn_voice = self.query_one("#btn-voice", Button)

        if self.state.interaction_mode == InteractionMode.TEXT:
            btn_text.add_class("mode-btn-active")
            btn_text.remove_class("mode-btn-inactive")
            btn_voice.add_class("mode-btn-inactive")
            btn_voice.remove_class("mode-btn-active")
        else:
            btn_voice.add_class("mode-btn-active")
            btn_voice.remove_class("mode-btn-inactive")
            btn_text.add_class("mode-btn-inactive")
            btn_text.remove_class("mode-btn-active")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-text":
            self.state.interaction_mode = InteractionMode.TEXT
        elif event.button.id == "btn-voice":
            self.state.interaction_mode = InteractionMode.VOICE
        self._update_buttons()
        # Notify app to handle mode change
        self.post_message(self.ModeChanged(self.state.interaction_mode))

    class ModeChanged(Message):
        def __init__(self, mode: InteractionMode) -> None:
            super().__init__()
            self.mode = mode
