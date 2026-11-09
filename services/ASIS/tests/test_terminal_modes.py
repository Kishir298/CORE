"""Display tests: mode switching + composer (no app restart, no I/O)."""

from __future__ import annotations

from asis.cli.terminal.modes import Composer, ModeController


def test_tab_switch_preserves_label():
    m = ModeController("TEXT")
    assert "TEXT" in m.label()
    assert m.handle_key("TAB") == "VOICE"
    assert "VOICE" in m.label()
    assert m.handle_key("TAB") == "TEXT"
    assert m.handle_key("ENTER") == "TEXT"


def test_composer_multiline_history_clear():
    c = Composer()
    c.type_line("hello")
    c.type_line("world")
    assert c.text() == "hello\nworld"
    assert c.submit() == "hello\nworld"
    assert c.text() == "" and c.history() == ["hello\nworld"]
    c.type_line("x")
    c.clear()
    assert c.text() == ""
    assert "TAB Mode" in c.hint() and "ESC Stop" in c.hint()
