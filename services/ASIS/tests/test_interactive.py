"""Deterministic tests for the persistent interactive terminal.

Mocks/fakes only: no microphone, speakers, Ollama, network, or GPU.
"""

from __future__ import annotations

import io
import threading

import pytest

from asis.cli.interactive.commands import parse_command
from asis.cli.interactive.keys import KeyWatcher
from asis.cli.interactive.loop import run_interactive
from asis.cli.interactive.renderer import TypingRenderer
from asis.cli.interactive.session import InteractiveSession
from asis.documents import DocumentStore


class FakeApp:
    """Minimal AssistantApp double with a real ConversationSession."""

    def __init__(self, replies=None):
        from asis.ai.conversation import ConversationSession

        self.session = ConversationSession()
        self._pending_memory_query = ""
        self._replies = list(replies or [])
        self._assembler_calls = 0

        def _ctx():
            self._assembler_calls += 1
            return ""

        self._assembler_context = _ctx
        self.chat_calls: list[str] = []

    def chat(self, message: str) -> str:
        self.chat_calls.append(message)
        self.session.add_user(message)
        reply = self._replies.pop(0) if self._replies else f"echo:{message}"
        self.session.add_assistant(reply)
        return reply


def _renderer(stream):
    return TypingRenderer(stream=stream, char_delay=0)


def _run(app, inputs, stream, **kwargs):
    it = iter(inputs)
    return run_interactive(
        app,
        input_fn=lambda p: next(it),
        renderer=_renderer(stream),
        stream=stream,
        max_turns=kwargs.pop("max_turns", 0),
        **kwargs,
    )


# -- startup / text / commands -------------------------------------------------


def test_startup_and_text_input():
    app = FakeApp()
    stream = io.StringIO()
    code = _run(app, ["hello", "/exit"], stream)
    assert code == 0
    out = stream.getvalue()
    assert "A.S.I.S." in out and "MODEL:" in out  # header + status panels
    assert "echo:hello" in out
    assert app.chat_calls == ["hello"]


def test_repeated_messages_keep_session():
    app = FakeApp()
    stream = io.StringIO()
    _run(app, ["one", "two", "three", "/exit"], stream)
    assert app.chat_calls == ["one", "two", "three"]
    roles = [m.role.value for m in app.session.messages]
    assert roles == ["user", "assistant"] * 3


def test_commands_not_sent_to_llm():
    app = FakeApp()
    stream = io.StringIO()
    _run(app, ["/help", "/docs", "/clear-docs", "/clear", "/exit"], stream)
    assert app.chat_calls == []
    out = stream.getvalue()
    assert "/mode" in out  # help text
    assert "Attachments: (none)" in out


def test_mode_commands():
    app = FakeApp()
    stream = io.StringIO()
    # /mode toggles text->voice; the voice typed-escape hook switches back;
    # then /exit leaves from text mode.
    typed = iter(["/mode", "/exit"])
    polls = iter(["/mode text"])

    def _poll():
        try:
            return next(polls)
        except StopIteration:
            return None

    code = run_interactive(
        app,
        input_fn=lambda p: next(typed),
        renderer=_renderer(stream),
        stream=stream,
        voice_poll=_poll,
        max_turns=5,
    )
    assert code == 0
    assert app.chat_calls == []
    out = stream.getvalue()
    assert "MODE: VOICE" in out
    assert "MODE: TEXT" in out


def test_exit_and_quit_and_shutdown_phrase():
    for cmd in ("/exit", "/quit", "asis shutdown"):
        app = FakeApp()
        stream = io.StringIO()
        assert _run(app, [cmd], stream) == 0
        assert app.chat_calls == []


def test_unknown_command_not_forwarded():
    app = FakeApp()
    stream = io.StringIO()
    _run(app, ["/frobnicate", "/exit"], stream)
    assert app.chat_calls == []
    assert "Unknown command" in stream.getvalue()


def test_parse_command_quoted_windows_path():
    cmd = parse_command('/upload "C:\\Docs\\research paper.pdf"')
    assert cmd is not None and cmd.arg.endswith("research paper.pdf")
    assert parse_command("hello") is None
    assert parse_command("/attach notes.md").arg == "notes.md"


# -- renderer / interrupts ------------------------------------------------------


def test_renderer_exact_output_no_extra_lines():
    stream = io.StringIO()
    stream.isatty = lambda: False
    text = "Hello! How can I help?"
    result = TypingRenderer(stream=stream, char_delay=0).render(text)
    assert result == text
    assert stream.getvalue().count("\n") == 1
    assert stream.getvalue() == f"A.S.I.S. > {text}\n"


def test_renderer_progressive_and_recoverable():
    stream = io.StringIO()
    stream.isatty = lambda: True
    stop = threading.Event()
    renderer = TypingRenderer(stream=stream, char_delay=0.001)
    # Interrupted render leaves a recoverable terminal ...
    partial = renderer.render("hello world response", stop_event=stop)
    assert partial == "hello world response"
    # ... and a stopped render reports interruption but stays usable.
    stop.set()
    partial2 = renderer.render("another response", stop_event=stop)
    assert partial2 == ""
    assert "[interrupted]" in stream.getvalue()
    stop.clear()
    assert renderer.render("ok") == "ok"


def test_esc_interrupts_render_not_app():
    # ESC flag stops rendering mid-stream; the app/session survives.
    stream = io.StringIO()
    stream.isatty = lambda: True
    stop = threading.Event()
    stop.set()
    renderer = TypingRenderer(stream=stream, char_delay=0.001)
    out = renderer.render("a long response", stop_event=stop)
    assert out == ""
    assert "[interrupted]" in stream.getvalue()
    # ... and the terminal is immediately reusable for the next response.
    stop.clear()
    assert renderer.render("recovered") == "recovered"


def test_ctrl_c_exits_and_cleans_up():
    app = FakeApp()
    stream = io.StringIO()
    cleaned = []

    def _boom(prompt):
        raise KeyboardInterrupt

    code = run_interactive(
        app,
        input_fn=_boom,
        renderer=_renderer(stream),
        stream=stream,
        cleanup=lambda: cleaned.append(True),
    )
    assert code == 0
    assert cleaned == [True]


def test_key_watcher_degrades_off_tty(monkeypatch):
    import sys as _sys

    monkeypatch.setattr(_sys.stdin, "isatty", lambda: False)
    watcher = KeyWatcher(on_esc=lambda: None)
    assert watcher.start() is False
    watcher.stop()


# -- voice ----------------------------------------------------------------------


def _mock_pipeline(transcript="what is a black hole"):
    from asis.voice import (
        MockAudioInput,
        MockAudioOutput,
        MockSpeakerIdentifier,
        MockSpeechRecognizer,
        MockTextToSpeech,
        VoicePipeline,
    )
    from asis.voice.models import AudioData

    tts = MockTextToSpeech()
    pipe = VoicePipeline(
        audio_input=MockAudioInput([AudioData(samples=[1], sample_rate=16000)]),
        speech_recognizer=MockSpeechRecognizer(text=transcript),
        speaker_identifier=MockSpeakerIdentifier(),
        tts=tts,
        audio_output=MockAudioOutput(),
    )
    return pipe, tts


def test_voice_turn_transcript_displayed_and_spoken():
    from asis.voice import MockTextToSpeech  # noqa: F401 (import surface check)

    app = FakeApp(replies=["A black hole is..."])
    pipe, tts = _mock_pipeline("what is a black hole")
    session = InteractiveSession(app, pipeline=pipe)
    turn = session.voice_turn()
    assert turn["transcript"] == "what is a black hole"
    assert turn["response"] == "A black hole is..."
    # Same final text went to TTS (pipeline.run_once speaks internally).
    assert tts.synthesized == ["A black hole is..."]


def test_voice_response_rendered_in_loop():
    app = FakeApp(replies=["A black hole is..."])
    pipe, tts = _mock_pipeline("tell me about black holes")
    stream = io.StringIO()
    code = _run(
        app,
        ["/mode voice"],
        stream,
        pipeline=pipe,
        max_turns=2,
    )
    assert code == 0
    out = stream.getvalue()
    assert "VOICE MODE" in out
    assert "tell me about black holes" in out and "You >" in out
    assert "A black hole is..." in out
    assert tts.synthesized == ["A black hole is..."]


def test_voice_unavailable_fails_gracefully():
    app = FakeApp()
    session = InteractiveSession(app, pipeline=None)
    with pytest.raises(RuntimeError, match="voice is unavailable"):
        session.voice_turn()


def test_voice_typed_escape_never_traps_user():
    # Even with a live mic pipeline, a typed /mode text returns to typing.
    app = FakeApp(replies=["voice reply", "text reply"])
    pipe, _ = _mock_pipeline("spoken words")
    stream = io.StringIO()
    typed = iter(["/mode voice", "/exit"])
    polls = iter(["/mode text"])

    def _poll():
        try:
            return next(polls)
        except StopIteration:
            return None

    code = run_interactive(
        app,
        pipeline=pipe,
        input_fn=lambda p: next(typed),
        renderer=_renderer(stream),
        stream=stream,
        voice_poll=_poll,
        max_turns=5,
    )
    assert code == 0
    assert "MODE: TEXT" in stream.getvalue()


def test_voice_tts_failure_handled_in_loop():
    app = FakeApp(replies=["spoken response"])

    class _BadTTS:
        def synthesize(self, text):
            raise RuntimeError("no speakers")

    from asis.voice import (
        MockAudioInput,
        MockAudioOutput,
        MockSpeakerIdentifier,
        MockSpeechRecognizer,
        VoicePipeline,
    )
    from asis.voice.models import AudioData

    pipe = VoicePipeline(
        audio_input=MockAudioInput([AudioData(samples=[1], sample_rate=16000)]),
        speech_recognizer=MockSpeechRecognizer(text="hi"),
        speaker_identifier=MockSpeakerIdentifier(),
        tts=_BadTTS(),
        audio_output=MockAudioOutput(),
    )
    stream = io.StringIO()
    code = _run(app, ["/mode voice"], stream, pipeline=pipe, max_turns=2)
    assert code == 0  # loop survives; error is reported, not raised
    assert "failed" in stream.getvalue().lower()


def test_mode_switch_keeps_conversation():
    app = FakeApp(replies=["Got it.", "Research aerodynamics."])
    pipe, _ = _mock_pipeline("What should I research next?")
    session = InteractiveSession(app, pipeline=pipe)
    session.chat_text("My project is about aircraft.")
    session.set_interaction_mode("voice")
    turn = session.voice_turn()
    assert turn["transcript"] == "What should I research next?"
    assert turn["response"] == "Research aerodynamics."
    session.set_interaction_mode("text")
    assert session.chat_text("and then?") == "echo:and then?"
    roles = [m.role.value for m in app.session.messages]
    assert roles == ["user", "assistant"] * 3
    assert "aircraft" in app.session.messages[0].content


# -- documents -------------------------------------------------------------------


def test_upload_and_docs_and_clear(tmp_path):
    app = FakeApp()
    stream = io.StringIO()
    target = tmp_path / "physics.pdf"
    target.write_bytes(b"%PDF-1.4\nthermodynamics entropy heat\n" + b"x" * 100)
    code = _run(
        app, [f"/upload {target}", "/docs", "/clear-docs", "/docs", "/exit"], stream
    )
    assert code == 0
    out = stream.getvalue()
    assert "Attachments:" in out and "physics.pdf" in out
    assert "Cleared attached documents." in out
    assert app.chat_calls == []


def test_supported_formats_ingested(tmp_path):
    store = DocumentStore()
    (tmp_path / "a.txt").write_text("plain text content")
    (tmp_path / "b.md").write_text("# title\nmarkdown content")
    (tmp_path / "c.json").write_text('{"key": "value here"}')
    (tmp_path / "d.csv").write_text("a,b\n1,2\n")
    for name in ("a.txt", "b.md", "c.json", "d.csv"):
        doc = store.attach(str(tmp_path / name))
        assert doc.text.strip()
    assert store.list_names() == ["a.txt", "b.md", "c.json", "d.csv"]


def test_unsupported_format_message(tmp_path):
    app = FakeApp()
    stream = io.StringIO()
    bad = tmp_path / "notes.xyz"
    bad.write_text("junk")
    _run(app, [f"/upload {bad}", "/exit"], stream)
    assert "can't read that file type" in stream.getvalue()
    assert app.chat_calls == []


def test_missing_file_message():
    app = FakeApp()
    stream = io.StringIO()
    _run(app, ["/upload /nonexistent/path.pdf", "/exit"], stream)
    assert "couldn't find" in stream.getvalue()


def test_document_context_available_to_inference(tmp_path):
    app = FakeApp(replies=["The doc says entropy increases."])
    session = InteractiveSession(app)
    target = tmp_path / "notes.md"
    target.write_text("thermodynamics: entropy of an isolated system increases.")
    session.docs.attach(str(target))
    reply = session.chat_text("summarize the document")
    assert reply == "The doc says entropy increases."
    # The wired assembler exposes bounded doc context for the same query.
    app._pending_memory_query = "summarize the document"
    context = app._assembler_context()
    assert "entropy" in context


def test_document_context_survives_mode_change(tmp_path):
    from asis.documents import build_document_context

    app = FakeApp()
    session = InteractiveSession(app)
    target = tmp_path / "notes.md"
    target.write_text("boundary layer content here")
    session.docs.attach(str(target))
    session.set_interaction_mode("voice")
    assert "boundary layer" in build_document_context(session.docs, "summarize")
    session.set_interaction_mode("text")
    assert session.docs.list_names() == ["notes.md"]


# -- entry wiring -----------------------------------------------------------------


def test_entry_single_shot_still_works(tmp_path, capsys):
    from asis.cli.main import entry

    code = entry(
        [
            "--provider",
            "mock",
            "--message",
            "Hello there!",
            "--memory-db",
            str(tmp_path / "m.db"),
        ]
    )
    assert code == 0
    assert capsys.readouterr().out.strip()


def test_entry_main_module():
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "asis", "--version"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0
    assert "A.S.I.S." in proc.stdout


def test_interactive_uses_qwen3_default():
    from asis.configuration import defaults

    assert defaults.AI_MODEL == "qwen3:14b"
    assert "qwen2.5:3b" not in defaults.AI_MODEL
