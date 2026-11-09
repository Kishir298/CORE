"""Terminal renderer: true streaming + legacy typing animation.

True streaming path: Ollama chunk -> provider -> engine -> ``on_chunk`` ->
``begin_stream/write_chunk/end_stream`` -> terminal without waiting for
completion. Legacy ``render()`` animates already-final text (kept for
voice turns, errors and non-streaming callers). The provider/engine never
knows about the terminal.
"""

from __future__ import annotations

import sys
import threading
import time


class TypingRenderer:
    """Renders ``A.S.I.S.`` responses progressively on the terminal."""

    def __init__(
        self,
        prefix: str = "A.S.I.S. > ",
        char_delay: float = 0.012,
        stream=None,
    ) -> None:
        self.prefix = prefix
        self.char_delay = max(0.0, float(char_delay))
        self.stream = stream if stream is not None else sys.stdout
        self._lock = threading.RLock()
        self._streaming = False

    def _tty(self) -> bool:
        try:
            return bool(self.stream.isatty())
        except Exception:
            return False

    def begin_stream(self) -> None:
        """Write the response prefix for a new streamed turn."""
        with self._lock:
            try:
                self.stream.write(self.prefix)
                self.stream.flush()
            except Exception:
                pass
            self._streaming = True

    def write_chunk(self, chunk: str) -> None:
        """Write one streamed chunk immediately (thread-safe, best-effort)."""
        if not chunk:
            return
        with self._lock:
            try:
                self.stream.write(chunk)
                self.stream.flush()
            except Exception:
                pass

    def end_stream(self, interrupted: bool = False) -> None:
        """Terminate the streamed line (newline, or [interrupted] marker)."""
        with self._lock:
            try:
                if interrupted:
                    self.stream.write("  [interrupted]\n")
                else:
                    self.stream.write("\n")
                self.stream.flush()
            except Exception:
                pass
            self._streaming = False

    def render(
        self,
        text: str,
        stop_event: threading.Event | None = None,
    ) -> str:
        """Render text with a typing animation; return what was shown.

        A set ``stop_event`` (ESC) stops mid-render and restores the line.
        Never raises on render errors; always ends with a newline.
        """
        final = text if isinstance(text, str) else str(text)
        try:
            self.stream.write(self.prefix)
            self.stream.flush()
        except Exception:
            return ""
        if not final:
            try:
                self.stream.write("\n")
                self.stream.flush()
            except Exception:
                pass
            return ""
        # Non-TTY (pipes/tests) or zero delay: single write, no animation.
        if not self._tty() or self.char_delay <= 0:
            try:
                self.stream.write(final + "\n")
                self.stream.flush()
            except Exception:
                pass
            return final
        shown: list[str] = []
        try:
            for ch in final:
                if stop_event is not None and stop_event.is_set():
                    self.stream.write("  [interrupted]\n")
                    self.stream.flush()
                    return "".join(shown)
                self.stream.write(ch)
                self.stream.flush()
                shown.append(ch)
                if ch != "\n":
                    time.sleep(self.char_delay)
            self.stream.write("\n")
            self.stream.flush()
        except Exception:
            try:
                self.stream.write("\n")
                self.stream.flush()
            except Exception:
                pass
        return "".join(shown) if shown else final
