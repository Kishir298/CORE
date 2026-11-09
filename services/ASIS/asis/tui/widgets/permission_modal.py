"""Permission Modal - Overlay for gated actions.

Centered modal with Allow/Deny buttons.
"""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Static

from asis.tui.state import AppState, PermissionRequest


class PermissionModal(ModalScreen):
    """Modal screen for permission requests."""

    DEFAULT_CSS = """
    PermissionModal {
        align: center middle;
    }

    PermissionModal > Vertical {
        width: 40;
        height: auto;
        max-height: 80%;
        background: #111820;
        border: solid #30363d;
        padding: 2;
    }

    PermissionModal .title {
        color: d29922;
        text-style: bold;
        width: 100%;
        content-align: center middle;
        margin-bottom: 1;
    }

    PermissionModal .message {
        color: #c9d1d9;
        width: 100%;
        margin-bottom: 1;
    }

    PermissionModal .tool-name {
        color: #5ee6d0;
        text-style: bold;
    }

    PermissionModal .buttons {
        width: 100%;
        height: 3;
        align: center middle;
        margin-top: 2;
    }

    PermissionModal .allow-btn {
        background: #3fb950;
        color: #0a0e14;
        margin-right: 2;
    }

    PermissionModal .deny-btn {
        background: #f85149;
        color: #0a0e14;
    }
    """

    def __init__(self, state: AppState, request: PermissionRequest) -> None:
        super().__init__()
        self.state = state
        self.request = request

    def compose(self) -> Widget:
        with Vertical():
            yield Static("Permission required", classes="title")
            yield Static("A.S.I.S. wants to execute:", classes="message")
            yield Static(f"[span.tool-name]{self.request.tool_name}[/span]", classes="message", markup=True)
            with Horizontal(classes="buttons"):
                yield Button("Allow", classes="allow-btn", id="allow")
                yield Button("Deny", classes="deny-btn", id="deny")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "allow":
            self.dismiss(True)
        elif event.button.id == "deny":
            self.dismiss(False)
