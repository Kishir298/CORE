"""Stdlib-only keyboard watcher: ESC interrupts, TAB switches mode, CTRL+C exits.

Windows uses ``msvcrt``; POSIX uses ``termios``/``tty`` + ``select``.
Degrades to a no-op when stdin is not a TTY (tests, pipes).
"""

from __future__ import annotations

import contextlib
import sys
import threading
from collections.abc import Callable


class KeyWatcher:
    """Watches for ESC (interrupt) and CTRL+C (shutdown) in the background.

    ESC invokes ``on_esc`` cooperatively. CTRL+C sets ``shutdown_event``
    (and invokes ``on_shutdown``) so the main loop can exit cleanly via a
    thread-safe mechanism — a background thread cannot raise
    ``KeyboardInterrupt`` in the main thread.
    """

    def __init__(
        self,
        on_esc: Callable[[], None] | None = None,
        on_shutdown: Callable[[], None] | None = None,
        shutdown_event: threading.Event | None = None,
        on_tab: Callable[[], None] | None = None,
    ) -> None:
        self._on_esc = on_esc
        self._on_shutdown = on_shutdown
        self._on_tab = on_tab
        self.shutdown_event = (
            shutdown_event if shutdown_event is not None else threading.Event()
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.active = False

    def start(self) -> bool:
        """Start watching. Returns True when a real watcher is running."""
        if self._thread is not None and self._thread.is_alive():
            return True
        try:
            if not sys.stdin.isatty():
                return False
        except Exception:
            return False
        self._stop.clear()
        self.shutdown_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.active = True
        return True

    def stop(self, timeout: float = 1.0) -> None:
        self._stop.set()
        self.active = False
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            with contextlib.suppress(Exception):
                thread.join(timeout=timeout)

    @property
    def shutdown_requested(self) -> bool:
        return self.shutdown_event.is_set()

    def request_shutdown(self) -> None:
        """Signal shutdown from any thread (CTRL+C path)."""
        self.shutdown_event.set()
        if self._on_shutdown is not None:
            with contextlib.suppress(Exception):
                self._on_shutdown()

    def _emit_esc(self) -> None:
        if self._on_esc is not None:
            with contextlib.suppress(Exception):
                self._on_esc()

    def _emit_tab(self) -> None:
        if self._on_tab is not None:
            with contextlib.suppress(Exception):
                self._on_tab()

    def _run(self) -> None:
        try:
            if sys.platform == "win32":
                self._run_windows()
            else:
                self._run_posix()
        except Exception:
            pass

    def _run_windows(self) -> None:
        import msvcrt

        while not self._stop.is_set():
            if msvcrt.kbhit():
                try:
                    ch = msvcrt.getwch()
                except Exception:
                    continue
                if ch == "\x1b":  # ESC
                    self._emit_esc()
                elif ch == "\x09":  # TAB: switch text <-> voice mode
                    self._emit_tab()
                elif ch == "\x03":  # CTRL+C
                    self.request_shutdown()
                    return
            self._stop.wait(0.05)

    def _run_posix(self) -> None:
        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while not self._stop.is_set():
                ready, _, _ = select.select([sys.stdin], [], [], 0.05)
                if not ready:
                    continue
                ch = sys.stdin.read(1)
                if ch == "\x1b":
                    self._emit_esc()
                elif ch == "\x09":  # TAB: switch text <-> voice mode
                    self._emit_tab()
                elif ch == "\x03":
                    self.request_shutdown()
                    return
        finally:
            # Always restore terminal state, even on exception/CTRL+C/ESC.
            with contextlib.suppress(Exception):
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
