"""Input Box - Right column input area.

Bordered box with:
- Top-left: "You >" prompt + live cursor/typed text
- Top-right: "[+] Attach" button
- Middle: empty vertical space for multiline
- Bottom-right: key hints dim gray
"""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Input, Static

from asis.tui.state import AppState


class InputBox(Widget):
    """Right column input box."""

    DEFAULT_CSS = """
    InputBox {
        width: 100%;
        height: 100%;
        border: solid #30363d;
        background: #0a0e14;
        padding: 1;
    }

    InputBox > Vertical {
        width: 100%;
        height: 100%;
    }

    InputBox .prompt-row {
        width: 100%;
        height: 1;
    }

    InputBox .prompt {
        color: #61dafb;
        width: auto;
    }

    InputBox Input {
        width: 1fr;
        background: #111820;
        border: none;
        color: #c9d1d9;
        padding: 0;
    }

    InputBox .attach-btn {
        width: auto;
        background: #111820;
        border: solid #30363d;
        color: #c9d1d9;
        margin-left: 1;
    }

    InputBox .attach-btn:hover {
        background: #5ee6d0;
        color: #0a0e14;
    }

    InputBox .hints {
        width: 100%;
        height: 1;
        content-align: right middle;
        color: #6e7681;
        text-style: dim;
        margin-top: 1;
    }

    InputBox .hint-key {
        color: #c9d1d9;
        text-style: bold;
    }
    """

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state

    def compose(self) -> Widget:
        with Vertical():
            with Horizontal(classes="prompt-row"):
                yield Static("You >", classes="prompt")
                yield Input(placeholder="Type a message...", id="input")
                yield Button("[+] Attach", classes="attach-btn", id="attach-btn")
            # Empty space for multiline (handled by Input height)
            yield Static("", id="spacer")
            yield Static(
                "[bold]Enter[/bold] Send  "
                "[bold]Shift+Enter[/bold] New Line  "
                "[bold]Esc[/bold] Cancel",
                classes="hints",
                markup=True
            )

    def on_mount(self) -> None:
        self._update()
        input_widget = self.query_one("#input", Input)
        input_widget.focus()

    def watch_state(self) -> None:
        self._update()

    def _update(self) -> None:
        input_widget = self.query_one("#input", Input)
        # Sync state to input (but don't override user typing)
        if not input_widget.has_focus:
            input_widget.value = self.state.input_text

    async def on_input_changed(self, event: Input.Changed) -> None:
        self.state.input_text = event.value

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter pressed - send message."""
        if event.value.strip():
            self.post_message(self.MessageSent(event.value.strip()))
            self.state.input_text = ""
            event.input.value = ""

    async def on_key(self, event: Key) -> None:
        """Handle special keys."""
        if event.key == "escape":
            self.post_message(self.InputCancelled())
        elif event.key == "shift+enter":
            # Allow multiline in input
            input_widget = self.query_one("#input", Input)
            cursor_pos = input_widget.cursor_position
            input_widget.value = input_widget.value[:cursor_pos] + "\n" + input_widget.value[cursor_pos:]
            input_widget.cursor_position = cursor_pos + 1
            self.state.input_text = input_widget.value
            event.prevent_default().stop()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "attach-btn":
            self.post_message(self.AttachClicked())

    class MessageSent(Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    class InputCancelled(Message):
        pass

    class AttachClicked(Message):
        pass
