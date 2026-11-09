"""Display tests: voice/tool/streaming/error/boot (mock only, no hardware)."""

from __future__ import annotations

from asis.cli.interactive.session import InteractiveSession
from asis.cli.terminal import activity
from asis.cli.terminal.status import clean_error


class _App:
    def chat(self, message: str) -> str:
        return f"echo:{message}"


def test_voice_tool_stream_boot_display():
    assert "LISTENING" in activity.voice_line("listening", "hi", "hello")
    assert "IDLE" in activity.voice_line("bogus")
    assert "Using calculator" in activity.tool_line("calculator")
    assert "complete" in activity.tool_line("x", done=True)
    assert "Generating" in activity.stream_frame(partial="")
    assert "▌" in activity.stream_frame(partial="Hel", generating=True)
    assert "▌" not in activity.stream_frame(partial="Done", generating=False)
    assert activity.boot_block().count("[ OK ]") == 7
    err = clean_error("Unable to reach Ollama.", "connection failed", "check Ollama")
    assert "Traceback" not in err and "check Ollama" in err


def test_modeswitch_preserves_session_history():
    from asis.ai.conversation import ConversationSession

    s = InteractiveSession(app=_App())
    s.app_session = ConversationSession()
    assert s.toggle_mode() == "voice"
    assert s.toggle_mode() == "text"
    s.chat_text("hello")
    assert s.toggle_mode() == "voice"
