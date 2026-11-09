"""Deterministic interrupt/shutdown/launcher/document-context tests.

Hardware/network free: no microphone, speaker, Ollama, GPU, or TTY required.
"""

from __future__ import annotations

import io
import logging
import threading

import pytest

from asis.cli.interactive.keys import KeyWatcher
from asis.cli.main import _normalize_argv, build_parser

# -- launcher -------------------------------------------------------------


def test_normalize_argv_basename_hardening():
    assert _normalize_argv(["C:\\x\\asis.exe", "--version"]) == ["--version"]
    assert _normalize_argv(["/usr/local/bin/asis", "--help"]) == ["--help"]
    assert _normalize_argv(["asis", "--version"]) == ["--version"]
    assert _normalize_argv(["__main__.py", "--version"]) == ["--version"]
    assert _normalize_argv(["--version"]) == ["--version"]
    assert _normalize_argv([]) == []
    # Must NOT strip lookalikes: basename comparison, not suffix match.
    assert _normalize_argv(["/opt/oasis", "--version"]) == ["/opt/oasis", "--version"]
    assert _normalize_argv(["--message", "asis"]) == ["--message", "asis"]


def test_explicit_model_override_still_parses():
    args = build_parser().parse_args(["--model", "qwen3:14b"])
    assert args.model == "qwen3:14b"
    args = build_parser().parse_args(["--model", "custom-model"])
    assert args.model == "custom-model"


# -- KeyWatcher: thread-safe shutdown contract ----------------------------


def test_keywatcher_shutdown_signal_no_keyboardinterrupt():
    calls: list[str] = []
    event = threading.Event()
    watcher = KeyWatcher(
        on_esc=lambda: calls.append("esc"),
        on_shutdown=lambda: calls.append("shutdown"),
        shutdown_event=event,
    )
    # ESC path only fires on_esc, never shutdown.
    watcher._emit_esc()
    assert calls == ["esc"]
    assert not watcher.shutdown_requested
    # CTRL+C path signals shutdown via event, never raises in caller thread.
    watcher.request_shutdown()
    assert watcher.shutdown_requested
    assert calls == ["esc", "shutdown"]
    watcher.stop()


def test_keywatcher_stop_joins_without_tty(monkeypatch):
    import sys as _sys

    monkeypatch.setattr(_sys.stdin, "isatty", lambda: False)
    watcher = KeyWatcher(on_esc=lambda: None)
    assert watcher.start() is False
    watcher.stop()  # must not hang or raise


# -- cooperative cancellation ---------------------------------------------


def test_inference_cooperative_cancel():
    from asis.ai.context import ContextAssembler
    from asis.ai.conversation import ConversationSession
    from asis.ai.inference import InferenceEngine
    from asis.errors import CancellationError
    from asis.identity import build_identity
    from asis.system.interrupt import InterruptCoordinator

    coordinator = InterruptCoordinator()
    token = coordinator.register("inference")
    token.cancel()
    assert coordinator.is_cancelled("inference") is True
    with pytest.raises(CancellationError):
        coordinator.check("inference")

    # Engine surfaces cancellation before/after provider call.
    class _Manager:
        def chat(self, messages):
            raise AssertionError("cancelled engine must not call provider")

    engine = InferenceEngine(
        manager=_Manager(),
        assembler=ContextAssembler(identity=build_identity()),
        interrupts=coordinator,
    )
    with pytest.raises(CancellationError):
        engine.generate(ConversationSession().messages)
    # Fresh registration resets so the next turn recovers.
    coordinator.register("inference")
    assert coordinator.is_cancelled("inference") is False


def test_interrupt_coordinator_cancel_all_and_recovery():
    from asis.system.interrupt import InterruptCoordinator

    coordinator = InterruptCoordinator()
    coordinator.register("inference")
    coordinator.register("voice")
    coordinator.register("tools")
    coordinator.cancel_all()
    assert coordinator.is_cancelled("inference")
    assert coordinator.is_cancelled("voice")
    assert coordinator.is_cancelled("tools")
    coordinator.register("inference")
    assert not coordinator.is_cancelled("inference")


# -- loop recovery after cancellation --------------------------------------


def test_loop_recovers_after_failed_turn():
    import io as _io

    from asis.cli.interactive.loop import run_interactive
    from asis.cli.interactive.renderer import TypingRenderer

    calls: list[str] = []

    class _Flaky:
        def chat(self, message: str) -> str:
            calls.append(message)
            if message == "boom":
                raise RuntimeError("provider down")
            return f"ok:{message}"

    stream = _io.StringIO()
    it = iter(["boom", "hello", "/exit"])
    code = run_interactive(
        _Flaky(),
        input_fn=lambda p: next(it),
        renderer=TypingRenderer(stream=stream, char_delay=0),
        stream=stream,
    )
    assert code == 0
    assert calls == ["boom", "hello"]
    assert "ok:hello" in stream.getvalue()


def test_loop_shutdown_event_exits_cleanly():
    """A requested shutdown during input still cleans up and exits 0."""

    import io as _io

    from asis.cli.interactive import loop as loop_mod
    from asis.cli.interactive.loop import run_interactive
    from asis.cli.interactive.renderer import TypingRenderer

    cleaned: list[bool] = []

    def _boom(prompt):
        raise KeyboardInterrupt

    stream = _io.StringIO()
    code = run_interactive(
        type("A", (), {"chat": lambda self, m: "x"})(),
        input_fn=_boom,
        renderer=TypingRenderer(stream=stream, char_delay=0),
        stream=stream,
        cleanup=lambda: cleaned.append(True),
    )
    assert code == 0
    assert cleaned == [True]
    assert loop_mod.run_interactive is not None


# -- mode switching persistence --------------------------------------------


def test_mode_switch_preserves_docs_and_history(tmp_path):
    from asis.cli.interactive.session import InteractiveSession
    from tests.test_interactive import FakeApp

    app = FakeApp(replies=["r1"])
    session = InteractiveSession(app)
    doc = tmp_path / "notes.txt"
    doc.write_text("entropy thermodynamics")
    session.docs.attach(str(doc))
    session.chat_text("hello")
    assert session.set_interaction_mode("voice") == "voice"
    assert session.set_interaction_mode("text") == "text"
    assert session.docs.list_names() == ["notes.txt"]
    assert app.chat_calls == ["hello"]
    assert len(app.session.messages) == 2


# -- document context reaches inference -------------------------------------


def test_document_contents_reach_assembler_context(tmp_path):
    from asis.cli.interactive.session import InteractiveSession
    from asis.documents import build_document_context
    from tests.test_interactive import FakeApp

    app = FakeApp(replies=["answer"])
    session = InteractiveSession(app)
    assert session.docs is not None
    target = tmp_path / "paper.txt"
    target.write_text("the reactor coolant entropy threshold is 42 kelvin")
    session.docs.attach(str(target))
    app._pending_memory_query = "what is the entropy threshold?"
    combined = app._assembler_context()
    assert "42 kelvin" in combined
    ctx = build_document_context(session.docs, "entropy threshold")
    assert "42 kelvin" in ctx


def test_oversized_and_malicious_docs_bounded(tmp_path):
    import zipfile

    from asis.documents import DocumentStore, parsers

    store = DocumentStore()
    big = tmp_path / "big.txt"
    big.write_bytes(b"A" * (parsers.MAX_FILE_BYTES + 16))
    try:
        store.attach(str(big))
    except ValueError as exc:
        assert "too large" in str(exc)
    else:
        raise AssertionError("oversized file must be rejected")

    # Zip bomb guard: too many entries rejected without extraction.
    bomb = tmp_path / "bomb.docx"
    with zipfile.ZipFile(bomb, "w") as zf:
        for i in range(parsers.MAX_DOCX_ENTRIES + 1):
            zf.writestr(f"word/part{i}.xml", "<w:p>junk</w:p>")
        zf.writestr("word/document.xml", "<w:p>hello</w:p>")
    doc = store.attach(str(bomb))
    assert doc.text == ""


def test_quoted_windows_path_attach(tmp_path):
    from asis.documents import DocumentStore

    target = tmp_path / "research paper.txt"
    target.write_text("boundary layer content")
    store = DocumentStore()
    doc = store.attach(f'"{target}"')
    assert doc.name == "research paper.txt"
    assert "boundary layer" in doc.text


# -- renderer edge cases -----------------------------------------------------


def test_renderer_unicode_multiline_empty():
    from asis.cli.interactive.renderer import TypingRenderer

    stream = io.StringIO()
    stream.isatty = lambda: False
    renderer = TypingRenderer(stream=stream, char_delay=0)
    assert renderer.render("") == ""
    assert stream.getvalue().endswith("\n")
    stream2 = io.StringIO()
    stream2.isatty = lambda: False
    text = "héllo wörld\nline2 ✓\nline3"
    assert TypingRenderer(stream=stream2, char_delay=0).render(text) == text
    assert stream2.getvalue() == f"A.S.I.S. > {text}\n"


# -- logging -----------------------------------------------------------------


def test_logging_no_duplicate_handlers_and_debug():
    from asis.logging.logger import configure_logging

    first = configure_logging()
    count = len(first.handlers)
    second = configure_logging()
    assert second is first
    assert len(second.handlers) == count

    args = build_parser().parse_args(["--debug"])
    from asis.cli.main import apply_cli_log_level

    apply_cli_log_level(args)
    assert logging.getLogger("asis").getEffectiveLevel() == logging.DEBUG
    # Restore quiet default for subsequent tests.
    apply_cli_log_level(build_parser().parse_args([]))
