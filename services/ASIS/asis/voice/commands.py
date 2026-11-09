"""
Explicit voice mode commands for A.S.I.S.

No fragile NLP classifier: only exact, low-risk phrases switch modes.
Explicit state remains authoritative; anything unrecognized returns None
and flows to the normal AssistantApp path.
"""

from __future__ import annotations

from asis.app.modes import AssistantMode

_CODING_PHRASES = (
    "switch to coding mode",
    "enable coding mode",
    "go to coding mode",
    "start coding mode",
    "enable ascs",
    "switch to ascs",
    "ascs mode",
)

_GENERAL_PHRASES = (
    "switch to general mode",
    "enable general mode",
    "go to general mode",
    "start general mode",
    "disable coding mode",
    "disable ascs",
    "exit coding mode",
    "exit translation mode",
    "disable translation mode",
)

_TRANSLATION_PHRASES = (
    "switch to translation mode",
    "enable translation mode",
    "go to translation mode",
    "start translation mode",
    "translation mode",
)


def parse_voice_mode_command(text: str) -> AssistantMode | None:
    """Return the requested mode for explicit switch phrases, else None."""
    normalized = (text or "").strip().casefold()
    if not normalized:
        return None
    if normalized in _CODING_PHRASES:
        return AssistantMode.CODING
    if normalized in _TRANSLATION_PHRASES:
        return AssistantMode.TRANSLATION
    if normalized in _GENERAL_PHRASES:
        return AssistantMode.GENERAL
    return None
