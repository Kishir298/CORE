"""
Data models for the A.S.I.S. AI subsystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class MessageRole(StrEnum):
    """Standard conversational roles used with AI models."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class AIMessage:
    """A message sent to or returned by an AI model."""

    role: MessageRole
    content: str
    # Optional attached payloads (e.g. images) for multimodal providers.
    # Text-only providers ignore these; see AIProvider.supports_vision.
    attachments: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.role, MessageRole):
            raise TypeError(f"Invalid message role: {self.role!r}.")

        if not isinstance(self.content, str):
            raise TypeError(
                f"Message content must be str, got {type(self.content).__name__}."
            )


@dataclass(frozen=True)
class NativeToolCall:
    """One provider-native tool invocation request (untrusted model output)."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise TypeError(f"Invalid tool call name: {self.name!r}.")
        if not isinstance(self.arguments, dict):
            raise TypeError(
                "Tool call arguments must be a dict, "
                f"got {type(self.arguments).__name__}."
            )


@dataclass(frozen=True)
class AIResponse:
    """Standard response returned by an AI provider."""

    content: str
    model: str
    provider: str
    metadata: dict[str, Any] = field(default_factory=dict)
    # Native tool calls requested by the model (empty when the model
    # answered directly or the provider lacks native tool support).
    tool_calls: tuple[NativeToolCall, ...] = ()
