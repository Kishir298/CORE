"""Bottom Status Bar - Full width, 1 line.

Left: mode, model, three colored dots
Right: shortcuts
"""

from __future__ import annotations

from textual.widget import Widget
from textual.widgets import Static

from asis.tui.state import AppState


class StatusBar(Widget):
    """Full-width bottom status bar."""

    DEFAULT_CSS = """
    StatusBar {
        width: 100%;
        height: 1;
        background: #111820;
        border: solid #30363d;
        border-top: solid #30363d;
        padding: 0 1;
    }

    StatusBar > Static {
        width: 100%;
        height: 1;
    }

    StatusBar .left-section {
        color: #c9d1d9;
    }

    StatusBar .right-section {
        color: #6e7681;
        text-style: dim;
        content-align: right middle;
    }

    StatusBar .mode-label {
        color: #5ee6d0;
        text-style: bold;
    }

    StatusBar .model-name {
        color: #c9d1d9;
    }

    StatusBar .dot-online {
        color: #3fb950;
    }

    StatusBar .dot-offline {
        color: #f85149;
    }

    StatusBar .shortcut-key {
        color: #c9d1d9;
        text-style: bold;
    }
    """

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state

    def compose(self) -> Widget:
        yield Static("", id="status-content")

    def on_mount(self) -> None:
        self._update()

    def watch_state(self) -> None:
        self._update()

    def _update(self) -> None:
        status = self.query_one("#status-content", Static)

        # Left section
        mode_text = self.state.interaction_mode.value
        ollama_dot = "●" if self.state.ollama_online else "○"
        ollama_class = "dot-online" if self.state.ollama_online else "dot-offline"
        mem_dot = "●" if self.state.memory_ready else "○"
        mem_class = "dot-online" if self.state.memory_ready else "dot-offline"
        tools_dot = "●" if self.state.tools_ready else "○"
        tools_class = "dot-online" if self.state.tools_ready else "dot-offline"

        left = (
            f"[mode-label]{mode_text} MODE[/mode-label]  "
            f"[model-name]{self.state.model_name}[/model-name]  "
            f"OLLAMA [{ollama_class}]{ollama_dot}[/{ollama_class}]  "
            f"MEMORY [{mem_class}]{mem_dot}[/{mem_class}]  "
            f"TOOLS [{tools_class}]{tools_dot}[/{tools_class}]"
        )

        # Right section - show Ctrl+B hint in narrow mode
        if self.state.terminal_width < 90:
            right = (
                "[shortcut-key]Ctrl+B[/shortcut-key] Sidebar  "
                "[shortcut-key]Ctrl+C[/shortcut-key] Exit  "
                "[shortcut-key]Esc[/shortcut-key] Cancel"
            )
        else:
            right = (
                "[shortcut-key]Ctrl+C[/shortcut-key] Exit  "
                "[shortcut-key]Esc[/shortcut-key] Cancel"
            )

        # Combine with spacing
        status.update(f"{left}  {right}")
