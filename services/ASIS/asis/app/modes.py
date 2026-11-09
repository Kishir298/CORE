"""
Assistant mode abstraction for A.S.I.S.

A mode changes behavior (system instructions, tools, context), never the
underlying AI provider/model instance. A.S.C.S. is the CODING mode of
A.S.I.S., not a second runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class AssistantMode(StrEnum):
    """Available assistant capability modes."""

    GENERAL = "general"
    CODING = "coding"
    TRANSLATION = "translation"


def parse_mode(value: str) -> AssistantMode:
    """Parse a user-supplied mode name (case-insensitive)."""
    if not isinstance(value, str):
        raise ValueError(f"Invalid assistant mode: {value!r}.")
    normalized = value.strip().lower()
    from asis.pi.policy import enabled, PolicyError
    if enabled() and normalized == "coding":
        raise PolicyError("Pi coding execution is disabled until an enforceable sandbox is validated. Use asis pi-chat --kind code for text-only code generation.")
    for mode in AssistantMode:
        if normalized == mode.value:
            return mode
    valid = ", ".join(m.value for m in AssistantMode)
    raise ValueError(f"Unknown assistant mode: {value!r} (expected one of: {valid}).")


@dataclass(frozen=True)
class ModeProfile:
    """Mode-specific behavior: instructions, tools and context rules."""

    mode: AssistantMode
    title: str
    instructions: str
    memory_rules_extra: tuple[str, ...] = field(default_factory=tuple)
