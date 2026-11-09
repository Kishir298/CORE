"""Persona-mode console tests (identity sim over a mock provider, no network)."""

from __future__ import annotations

import io

from asis.ai.conversation import ConversationSession
from asis.ai.providers import MockAIProvider
from asis.cli.interactive.loop import run_interactive
from asis.cli.interactive.renderer import TypingRenderer
from asis.identities.pipeline import analyze_conversation
from asis.identities.store import IdentityStore

SAMPLE = """[12/03/24, 10:00:00] Alex: hey bro 😂
[12/03/24, 10:01:00] Me: lol hey! how was football?
[12/03/24, 10:02:00] Alex: it was great
[12/03/24, 10:05:00] Me: nice!
"""


class _App:
    def __init__(self, provider):
        self.session = ConversationSession()
        self.ai = type("A", (), {"provider": provider})()
        self._assembler_context = lambda: ""
        self.chat_calls: list[str] = []

    def chat(self, message: str) -> str:
        self.chat_calls.append(message)
        return f"echo:{message}"


def _renderer(stream):
    return TypingRenderer(stream=stream, char_delay=0)


def _seed(tmp_path) -> str:
    p = tmp_path / "Chat_A.txt"
    p.write_text(SAMPLE, encoding="utf-8")
    db = tmp_path / "ids.db"
    analyze_conversation(db, p, IdentityStore(db), "Chat_A")
    return str(db)


def _run(app, inputs, stream, **kw):
    it = iter(inputs)
    return run_interactive(
        app,
        input_fn=lambda p: next(it),
        renderer=_renderer(stream),
        stream=stream,
        **kw,
    )


def test_persona_list_enter_stream_and_exit(tmp_path):
    from asis.cli.interactive.persona import PersonaConsole

    db = _seed(tmp_path)
    provider = MockAIProvider(model="mock", responses=("hey buddy, all good",))
    app = _App(provider)
    console = PersonaConsole(app, db_path=db)
    assert "Alex" in console.names()
    assert console.enter("Alex") == "Alex"
    assert console.notice() is not None
    assert console.notice() is None  # once per session
    assert console.exit() == "Alex"
    assert console.active() is None


def test_persona_chat_streams_and_never_hits_app(tmp_path):
    db = _seed(tmp_path)
    provider = MockAIProvider(model="mock", responses=("hey buddy, all good",))
    app = _App(provider)
    stream = io.StringIO()
    code = _run(
        app,
        ["/persona Alex", "sup bro", "/persona off", "/exit"],
        stream,
        identities_db=db,
    )
    assert code == 0
    out = stream.getvalue()
    assert "[persona] Simulating Alex" in out
    assert "reconstructions" in out
    assert "hey buddy, all good" in out
    assert "A.S.I.S. >" in out
    # The persona answered; the assistant app was never invoked.
    assert app.chat_calls == []


def test_persona_unknown_and_list(tmp_path):
    db = _seed(tmp_path)
    provider = MockAIProvider(model="mock", responses=("x",))
    app = _App(provider)
    stream = io.StringIO()
    code = _run(
        app,
        ["/persona Nope", "/personas", "/exit"],
        stream,
        identities_db=db,
    )
    assert code == 0
    out = stream.getvalue()
    assert "Unknown identity: Nope" in out
    assert "Available personas" in out and "Alex" in out
    assert app.chat_calls == []


def test_persona_mode_default_turn_still_normal(tmp_path):
    # No /persona command: normal assistant flow untouched by the console.
    provider = MockAIProvider(model="mock", responses=("echo:hello",))
    app = _App(provider)
    stream = io.StringIO()
    _run(app, ["hello", "/exit"], stream, identities_db=tmp_path)
    assert app.chat_calls == ["hello"]


def test_persona_without_provider_reports_cleanly(tmp_path):
    db = _seed(tmp_path)
    app = _App(None)
    stream = io.StringIO()
    _run(app, ["/persona Alex", "hey", "/persona off", "/exit"], stream, identities_db=db)
    out = stream.getvalue()
    assert "failed" in out.lower() or "provider" in out.lower()
