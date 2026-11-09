"""Compact persistent status bar (text indicators, never color-only)."""

from __future__ import annotations


def status_bar(
    model: str = "qwen3:14b",
    mode: str = "TEXT",
    ollama: bool = True,
    voice: str = "READY",
    memory: bool = True,
    tools: bool = True,
) -> str:
    o = "●" if ollama else "○"
    m = "●" if memory else "○"
    t = "●" if tools else "○"
    return (
        f"MODEL: {model}  MODE: {mode}  OLLAMA: {o}  "
        f"VOICE: {voice}  MEMORY: {m}  TOOLS: {t}"
    )


def voice_strip(state: str = "IDLE") -> str:
    state = (state or "IDLE").upper()
    allowed = {"LISTENING", "PROCESSING", "SPEAKING", "IDLE", "ERROR"}
    if state not in allowed:
        state = "IDLE"
    dot = "●" if state in {"LISTENING", "SPEAKING"} else "○"
    return f"VOICE {dot} {state}  (LISTENING/PROCESSING/SPEAKING have text equivalents)"


def clean_error(title: str, status: str, action: str) -> str:
    return f"⚠ {title}\nStatus: {status}\nAction: {action}"
