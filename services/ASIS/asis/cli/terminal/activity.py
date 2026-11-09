"""Voice states, tool activity, streaming and error display (no mic/model).

All helpers are pure display over existing backend states:
VoiceRunner/pipeline statuses, tool events, TypingRenderer chunk API.
"""

from __future__ import annotations

VOICE_STATES = ("LISTENING", "PROCESSING", "SPEAKING", "IDLE", "ERROR")


def voice_line(state: str, transcript: str = "", reply: str = "") -> str:
    state = (state or "IDLE").upper()
    if state not in VOICE_STATES:
        state = "IDLE"
    lines = ["VOICE MODE", f"● {state}" if state != "IDLE" else "○ IDLE"]
    if transcript:
        lines.append(f"You (voice): {transcript}")
    if reply:
        lines.append(f"A.S.I.S. (voice): {reply}")
    return "\n".join(lines)


def tool_line(name: str, done: bool = False) -> str:
    if done:
        return "✓ Tool complete"
    return f"● Using {name}..."


def stream_frame(prefix: str = "A.S.I.S.", partial: str = "", generating: bool = True) -> str:
    cursor = " ▌" if generating else ""
    if generating and not partial:
        return f"{prefix}\n▌ Generating..."
    return f"{prefix}\n{partial}{cursor}"


def boot_block(lines: list[str] | None = None) -> str:
    rows = lines if lines else [
        "[BOOT] Starting A.S.I.S.",
        "[ OK ] Configuration loaded",
        "[ OK ] Identity loaded",
        "[ OK ] Personality loaded",
        "[ OK ] Memory initialized",
        "[ OK ] Tools initialized",
        "[ OK ] Ollama ready",
        "[ OK ] Model ready",
        "A.S.I.S. ready.",
    ]
    return "A.S.I.S.\n" + "\n".join(rows)
