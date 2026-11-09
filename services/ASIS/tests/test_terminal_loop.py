"""Wiring tests: terminal panels inside the live interactive loop (mock app)."""

from __future__ import annotations

import io

from asis.ai.conversation import ConversationSession
from asis.cli.interactive.keys import KeyWatcher
from asis.cli.interactive.loop import run_interactive
from asis.cli.interactive.renderer import TypingRenderer


class _App:
    def __init__(self):
        self.session = ConversationSession()
        self._assembler_context = lambda: ""
        self.chat_calls: list[str] = []

    def chat(self, message: str) -> str:
        self.chat_calls.append(message)
        return f"echo:{message}"


def _run(app, inputs, stream, **kw):
    it = iter(inputs)
    return run_interactive(
        app,
        input_fn=lambda p: next(it),
        renderer=TypingRenderer(stream=stream, char_delay=0),
        stream=stream,
        **kw,
    )


def test_startup_panels_and_legacy_strings():
    app, stream = _App(), io.StringIO()
    assert _run(app, ["hello", "/exit"], stream) == 0
    out = stream.getvalue()
    assert "A.S.I.S." in out and "MODEL:" in out  # header + status panels
    assert "echo:hello" in out  # streamed response content
    assert "[Enter] Send" in out  # footer goodbye panel


def test_composer_and_user_bubble_and_mode_status():
    app, stream = _App(), io.StringIO()
    assert _run(app, ["hello", "/mode voice", "/mode text", "/exit"], stream, max_turns=8) == 0
    out = stream.getvalue()
    assert "TEXT" in out and "VOICE MODE" in out
    assert "MODEL:" in out  # status refresh on /mode


def test_tab_callback_and_attach_error_frame(tmp_path):
    hits: list[str] = []
    w = KeyWatcher(on_tab=lambda: hits.append("tab"))
    w._emit_tab()
    assert hits == ["tab"]
    app, stream = _App(), io.StringIO()
    assert _run(app, ["/upload /nope/missing.txt", "/exit"], stream) == 0
    out = stream.getvalue()
    assert "couldn't find that file" in out
    assert "⚠" in out
