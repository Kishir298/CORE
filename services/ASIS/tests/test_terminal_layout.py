"""Display-only tests for terminal layout + status bar (no model/mic)."""

from __future__ import annotations

from asis.cli.terminal import layout
from asis.cli.terminal import status as statusmod


def test_header_footer_panels():
    h = layout.header()
    assert "A.S.I.S." in h and "ONLINE" in h
    assert "OFFLINE" in layout.header(online=False)
    assert "A Smart Intelligence System" in layout.header()
    f = layout.footer()
    assert "[Enter] Send" in f and "Ctrl+C" in f


def test_status_panel_rows():
    p = layout.status_panel()
    assert "MODEL:" in p and "qwen3:14b" in p
    assert "OLLAMA:" in p and "ONLINE" in p
    assert "MEMORY:" in p and "READY" in p
    assert "TOOLS:" in p and "READY" in p
    assert "VOICE:" in p and "READY" in p


def test_bottom_strip():
    s = layout.bottom_strip()
    assert "MODE" in s and "qwen3:14b" in s
    assert "LISTENING" in s and "SPEAKING" in s
    assert "○" in layout.bottom_strip(ollama=False)


def test_bubbles_badges_composer():
    assert layout.user_bubble("hello") == "You > hello"
    assert layout.assistant_bubble("Hello") == "A.S.I.S. > Hello"
    assert "▌" in layout.assistant_bubble("Hi", streaming=True)
    assert "[TOOL]" in layout.tool_badge("calc")
    assert "[DONE]" in layout.tool_badge("calc", done=True)
    assert "(none)" in layout.attachments_bar([])
    assert "physics_notes.pdf" in layout.attachments_bar(["physics_notes.pdf"])
    assert "×" in layout.attachments_bar(["physics_notes.pdf"])
    c = layout.composer(mode="VOICE", attachments=["a.pdf"], generating=True)
    assert "VOICE" in c and "Generating" in c
    assert "[+] Attach" in c


def test_status_voice_error_text():
    bar = statusmod.status_bar()
    assert "MODEL:" in bar and "MODE:" in bar and "OLLAMA:" in bar
    assert "LISTENING" in statusmod.voice_strip("listening")
    assert "IDLE" in statusmod.voice_strip("bogus")
    err = statusmod.clean_error("Unable to reach Ollama.", "connection failed", "check Ollama")
    assert "⚠" in err and "Traceback" not in err


def test_narrow_width_no_overflow():
    h = layout.header(width=40)
    assert len(h.splitlines()[0]) <= 42
