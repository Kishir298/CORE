"""
Base interface for A.S.I.S. AI providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from typing import Any

from ..models import AIMessage, AIResponse


class AIProvider(ABC):
    """Interface implemented by every AI backend."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider name."""
        raise NotImplementedError

    @property
    @abstractmethod
    def model(self) -> str:
        """Return the active model name."""
        raise NotImplementedError

    @abstractmethod
    def chat(
        self,
        messages: Sequence[AIMessage],
    ) -> AIResponse:
        """Generate a response from a conversation."""
        raise NotImplementedError

    @abstractmethod
    def stream_chat(
        self,
        messages: Sequence[AIMessage],
    ) -> Iterator[str]:
        """Stream a response as text chunks."""
        raise NotImplementedError

    @abstractmethod
    def available(self) -> bool:
        """Return whether the provider is currently available."""
        raise NotImplementedError

    @property
    def supports_native_tools(self) -> bool:
        """Return whether the provider can request native tool calls.

        Providers without native function-calling support leave the
        default (False); the application then uses the heuristic
        tool-intent fallback.
        """
        return False

    @property
    def supports_vision(self) -> bool:
        """Return whether the provider accepts image attachments.

        Text-only providers leave the default (False); the terminal
        then shows 'Image attachment unavailable for current model.'
        instead of crashing.
        """
        return False

    def chat_with_tools(
        self,
        messages: Sequence[AIMessage],
        tools: Sequence[Any],
    ) -> AIResponse:
        """Generate a response with native tool definitions available.

        ``tools`` are provider-neutral ``ToolDefinition`` records; each
        provider renders them into its own wire format. Returns an
        AIResponse whose ``tool_calls`` carries the model's structured
        invocations (empty when it answered directly). The default
        implementation reports lack of support; capable providers
        override it.
        """
        from asis.errors import InferenceError

        raise InferenceError(
            f"Provider {self.name!r} does not support native tool calling."
        )
