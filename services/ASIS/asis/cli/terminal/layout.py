"""ANSI terminal chrome matching the A.S.I.S. CLI reference (CLI.jpeg).

Pure display helpers (return strings, no I/O, no model calls) so visual
tests stay deterministic on a low-capability machine. Layout blocks:

  header        title + tagline + online indicator
  status_panel  left column: MODEL / OLLAMA / MEMORY / TOOLS / VOICE
  bubbles       ``You >`` / ``A.S.I.S. >`` arrow lines (streaming caret)
  tool_badge    ``[TOOL] name`` / ``[DONE] detail``
  attachments   ``Attachments: @ name ×`` chips
  composer      mode row + attach button + input prompt + hints + strip
"""

from __future__ import annotations

import shutil

MIN_WIDTH = 40
DEFAULT_WIDTH = 80
TAGLINE = "A Smart Intelligence System"


def terminal_width(default: int = DEFAULT_WIDTH) -> int:
    try:
        return max(MIN_WIDTH, shutil.get_terminal_size().columns)
    except Exception:
        return default


def _rule(width: int) -> str:
    width = max(MIN_WIDTH, int(width))
    return "─" * (width - 2)


def header(
    title: str = "A.S.I.S.",
    online: bool = True,
    tagline: str = TAGLINE,
    width: int = DEFAULT_WIDTH,
) -> str:
    """Top banner: title, tagline and online/offline state."""
    state = "● ONLINE" if online else "○ OFFLINE"
    bar = _rule(width)
    return (
        f"┌{bar}┐\n"
        f"│ {title}{' ' * max(1, width - 4 - len(title) - len(state))}{state} │\n"
        f"│ {tagline}{' ' * max(0, width - 4 - len(tagline))} │\n"
        f"├{bar}┤"
    )


def status_panel(
    model: str = "qwen3:14b",
    online: bool = True,
    memory: bool = True,
    tools: bool = True,
    voice: str = "READY",
) -> str:
    """Left status column from the reference design (label + value rows)."""
    ollama = "● ONLINE" if online else "○ OFFLINE"
    mem = "● READY" if memory else "○ OFFLINE"
    tl = "● READY" if tools else "○ OFFLINE"
    vc = f"● {voice}" if voice else "○ OFFLINE"
    return (
        f"MODEL:     {model}\n"
        f"OLLAMA:    {ollama}\n"
        f"MEMORY:    {mem}\n"
        f"TOOLS:     {tl}\n"
        f"VOICE:     {vc}"
    )


def bottom_strip(
    mode: str = "TEXT",
    model: str = "qwen3:14b",
    ollama: bool = True,
    memory: bool = True,
    tools: bool = True,
    voice: str = "READY",
) -> str:
    """Persistent bottom status strip (mode/model/subsystem dots)."""
    o = "●" if ollama else "○"
    m = "●" if memory else "○"
    t = "●" if tools else "○"
    vc = "●" if voice else "○"
    return (
        f"{mode} MODE, {model}, OLLAMA {o}, MEMORY {m}, TOOLS {t}\n"
        f"VOICE {vc} {voice or 'IDLE'}  ● LISTENING  ● PROCESSING  ● SPEAKING"
    )


def footer(width: int = DEFAULT_WIDTH) -> str:
    """Key-hint bar under the composer (reference: Enter/Esc/Ctrl+C)."""
    hints = (
        "[Enter] Send  [Shift+Enter] New Line  [Esc] Cancel  "
        "[Ctrl+C] Exit"
    )
    bar = _rule(width)
    return f"├{bar}┤\n│ {hints}{' ' * max(0, width - 4 - len(hints))} │\n└{bar}┘"


def user_bubble(text: str, width: int = DEFAULT_WIDTH) -> str:
    """User line in the reference arrow style (``You > ...``)."""
    del width  # arrow style is width-independent; kept for call compat
    return f"You > {(text or '').strip()}"


def assistant_bubble(
    text: str, streaming: bool = False, width: int = DEFAULT_WIDTH
) -> str:
    """Assistant line in the reference arrow style (``A.S.I.S. > ...``)."""
    del width
    cursor = " ▌" if streaming else ""
    return f"A.S.I.S. > {(text or '').strip()}{cursor}"


def tool_badge(name: str, done: bool = False) -> str:
    state = "[DONE]" if done else "[TOOL]"
    return f"{state} {name}"


def _chip(name: str) -> str:
    return f"@ {name} ×"


def attachments_bar(names: list[str]) -> str:
    """Attachment chips row (``@ name ×``), one line, from the design."""
    if not names:
        return "Attachments: (none)"
    return "Attachments:  " + "  ".join(_chip(n) for n in names)


def composer(
    mode: str = "TEXT",
    attachments: list[str] | None = None,
    generating: bool = False,
    width: int = DEFAULT_WIDTH,
) -> str:
    """Composer block: mode toggle, attach button, prompt and key hints."""
    atts = attachments_bar(attachments or [])
    status = "▌ Generating..." if generating else "> Type a message..."
    mode_row = f"MODE: {mode}  [ {'VOICE' if mode.upper() == 'TEXT' else 'TEXT' } ]      [+] Attach"
    hints = "[Enter] Send  [Shift+Enter] New Line  [Esc] Cancel"
    return f"{mode_row}\n{atts}\n{status}\n{hints}"
