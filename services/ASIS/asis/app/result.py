"""
Conversation outcome produced by processing one message.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProcessResult:
    """Result of handling a single user message."""

    stopped: bool = False
    interrupted: bool = False
    assistant_text: str = ""
    system_messages: list[str] = field(default_factory=list)
