"""Tool-event hooks: engine events -> terminal badges (mock bus/app)."""

from __future__ import annotations

import io

from asis.cli.interactive.loop import run_interactive
from asis.cli.interactive.renderer import TypingRenderer
from asis.events.bus import EventBus
from asis.events.events import Event, EventType


class _ToolApp:
    def __init__(self):
        from asis.ai.conversation import ConversationSession

        self.session = ConversationSession()
        self._assembler_context = lambda: ""
        self.event_bus = EventBus()
        self.chat_calls: list[str] = []

    def chat_streamed(self, message, on_chunk=None):
        self.chat_calls.append(message)
        self.event_bus.publish(
            Event(type=EventType.TOOL_EXECUTION_STARTED, data={"tool": "calculator"})
        )
        if on_chunk is not None:
            on_chunk("4")
        self.event_bus.publish(
            Event(type=EventType.TOOL_EXECUTION_FINISHED, data={"tool": "calculator"})
        )
        return "4"


def test_tool_badges_render_and_unsubscribed():
    app, stream = _ToolApp(), io.StringIO()
    it = iter(["calc this", "/exit"])
    code = run_interactive(
        app,
        input_fn=lambda p: next(it),
        renderer=TypingRenderer(stream=stream, char_delay=0),
        stream=stream,
    )
    assert code == 0
    out = stream.getvalue()
    assert "[TOOL] calculator" in out
    assert "[DONE] calculator" in out
    assert app.event_bus.subscriber_count(EventType.TOOL_EXECUTION_STARTED) == 0
    assert app.event_bus.subscriber_count(EventType.TOOL_EXECUTION_FINISHED) == 0


def test_streaming_delivers_chunks_incrementally():
    """Chunks reach the terminal as they arrive (no wait-for-full-answer)."""
    from asis.events.bus import EventBus

    writes: list[str] = []

    class _RecRenderer(TypingRenderer):
        def write_chunk(self, chunk):
            writes.append(chunk)
            return super().write_chunk(chunk)

    class _ChunkApp:
        def __init__(self):
            from asis.ai.conversation import ConversationSession

            self.session = ConversationSession()
            self._assembler_context = lambda: ""
            self.event_bus = EventBus()

        def chat_streamed(self, message, on_chunk=None):
            for ch in ["Hel", "lo", "!"]:
                on_chunk(ch)
            return "Hello!"

    app, stream = _ChunkApp(), io.StringIO()
    it = iter(["go", "/exit"])
    code = run_interactive(
        app,
        input_fn=lambda p: next(it),
        renderer=_RecRenderer(stream=stream, char_delay=0),
        stream=stream,
    )
    assert code == 0
    assert writes == ["Hel", "lo", "!"]  # progressive, not one batch
    assert "Hello!" in stream.getvalue()


def test_no_bus_no_badges_still_answers():
    from asis.cli.interactive.session import InteractiveSession

    class _Plain:
        def __init__(self):
            from asis.ai.conversation import ConversationSession

            self.session = ConversationSession()
            self._assembler_context = lambda: ""

        def chat(self, message):
            return f"echo:{message}"

    app, stream = _Plain(), io.StringIO()
    it = iter(["hello", "/exit"])
    code = run_interactive(
        app,
        input_fn=lambda p: next(it),
        renderer=TypingRenderer(stream=stream, char_delay=0),
        stream=stream,
    )
    assert code == 0
    assert "[TOOL]" not in stream.getvalue()
    assert "echo:hello" in stream.getvalue()
    assert isinstance(InteractiveSession(app, None).interaction_mode, str)
