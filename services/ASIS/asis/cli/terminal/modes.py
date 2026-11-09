"""Mode controller + input composer (display state only, session-owned data).

TAB switches TEXT<->VOICE without restarting the app; conversation,
memory, attachments and session are owned by InteractiveSession and
untouched here — this module only tracks display state.
"""

from __future__ import annotations

from collections import deque

MODES = ("TEXT", "VOICE")
SHORTCUTS = {"TAB": "switch mode", "ENTER": "send", "ESC": "stop", "CTRL+C": "exit"}


class ModeController:
    """Visible mode state; TAB toggles, session data preserved by caller."""

    def __init__(self, mode: str = "TEXT") -> None:
        self.mode = "VOICE" if (mode or "").upper() == "VOICE" else "TEXT"

    def handle_key(self, key: str) -> str:
        if (key or "").upper() == "TAB":
            self.mode = "VOICE" if self.mode == "TEXT" else "TEXT"
        return self.mode

    def label(self) -> str:
        other = "VOICE" if self.mode == "TEXT" else "TEXT"
        return f"MODE: [ {self.mode} ] [ {other} ]"


class Composer:
    """Multiline input buffer with history (display only)."""

    def __init__(self, limit: int = 50) -> None:
        self._buf: list[str] = []
        self._history: deque[str] = deque(maxlen=limit)

    def type_line(self, line: str) -> None:
        self._buf.append(line or "")

    def text(self) -> str:
        return "\n".join(self._buf)

    def submit(self) -> str:
        msg = self.text().strip()
        self._buf.clear()
        if msg:
            self._history.append(msg)
        return msg

    def clear(self) -> None:
        self._buf.clear()

    def history(self) -> list[str]:
        return list(self._history)

    def hint(self) -> str:
        return "ENTER Send   SHIFT+ENTER New Line   ESC Stop   TAB Mode   CTRL+C Exit"
