"""
Conversation session management for A.S.I.S.

Sessions hold the message history that gets sent to the AI model.
History is trimmed to a configured maximum so requests stay bounded.
"""

from __future__ import annotations

from asis.configuration.settings import settings

from .models import AIMessage, MessageRole


class ConversationSession:
    """A bounded conversation history."""

    def __init__(self, max_history: int | None = None) -> None:
        self._max_history = max_history or settings.conversation.max_history
        self._messages: list[AIMessage] = []

    def __len__(self) -> int:
        return len(self._messages)

    def __iter__(self):
        return iter(self._messages)

    @property
    def messages(self) -> list[AIMessage]:
        """Return the message history (system prompt excluded)."""
        return list(self._messages)

    def _append(self, role: MessageRole, content: str) -> AIMessage:
        message = AIMessage(role=role, content=content)
        self._messages.append(message)
        self._trim()
        return message

    def _trim(self) -> None:
        if len(self._messages) > self._max_history:
            self._messages = self._messages[-self._max_history :]

    def add_user(self, content: str) -> AIMessage:
        """Append a user message."""
        return self._append(MessageRole.USER, content)

    def add_assistant(self, content: str) -> AIMessage:
        """Append an assistant message."""
        return self._append(MessageRole.ASSISTANT, content)

    def add_system(self, content: str) -> AIMessage:
        """Append a system message."""
        return self._append(MessageRole.SYSTEM, content)

    def last(self) -> AIMessage | None:
        """Return the most recent message, if any."""
        return self._messages[-1] if self._messages else None

    def pop(self) -> AIMessage | None:
        """Remove and return the most recent message."""
        if not self._messages:
            return None

        return self._messages.pop()

    def clear(self) -> None:
        """Drop the entire history."""
        self._messages.clear()
