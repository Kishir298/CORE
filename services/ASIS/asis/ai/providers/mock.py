"""
Deterministic in-memory AI provider for A.S.I.S.

Used by tests and as a zero-dependency fallback when no AI backend is
available. Responses are configurable so behavior can be scripted.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Sequence
from typing import Any

from ..models import AIMessage, AIResponse, NativeToolCall
from .base import AIProvider


class MockAIProvider(AIProvider):
    """Scriptable AI provider that never touches the network."""

    def __init__(
        self,
        model: str = "mock",
        responses: Iterable[str] = ("This is a mock response.",),
        *,
        fail: bool = False,
        delay: float = 0.0,
        metadata: dict | None = None,
        tool_sequences: Iterable[Sequence[dict | NativeToolCall] | None] | None = None,
    ) -> None:
        self._model = model
        self._pool = list(responses)
        self.fail = fail
        self.delay = delay
        self.metadata = metadata or {}
        self._index = 0
        # Scripted native tool calls, one entry per chat_with_tools call:
        # a list of {"name":..., "arguments":...} (or NativeToolCall), or
        # None/empty for "answered directly". None (default) disables
        # native support, exercising the heuristic fallback instead.
        self._tool_sequences = (
            list(tool_sequences) if tool_sequences is not None else None
        )
        self._tool_index = 0
        self.last_tools: list[Any] | None = None

    @property
    def name(self) -> str:
        return "mock"

    @property
    def model(self) -> str:
        return self._model

    def available(self) -> bool:
        return not self.fail

    def _next_response(self) -> str:
        if not self._pool:
            return ""

        response = self._pool[self._index % len(self._pool)]
        self._index += 1
        return response

    def chat(
        self,
        messages: Sequence[AIMessage],
    ) -> AIResponse:
        if self.fail:
            raise ConnectionError("Mock AI provider is configured to fail.")

        if self.delay:
            time.sleep(self.delay)

        return AIResponse(
            content=self._next_response(),
            model=self._model,
            provider=self.name,
            metadata={"mock": True, **self.metadata},
        )

    @property
    def supports_native_tools(self) -> bool:
        return self._tool_sequences is not None

    def chat_with_tools(
        self,
        messages: Sequence[AIMessage],
        tools: Sequence[Any],
    ) -> AIResponse:
        if self._tool_sequences is None:
            from asis.errors import InferenceError

            raise InferenceError("Mock provider has native tools disabled.")
        if self.fail:
            raise ConnectionError("Mock AI provider is configured to fail.")
        if self.delay:
            time.sleep(self.delay)
        self.last_tools = list(tools)
        if self._tool_index < len(self._tool_sequences):
            scripted = self._tool_sequences[self._tool_index]
        else:
            scripted = None
        self._tool_index += 1
        calls: list[NativeToolCall] = []
        for entry in scripted or []:
            if isinstance(entry, NativeToolCall):
                calls.append(entry)
            elif isinstance(entry, dict):
                name = entry.get("name", "")
                arguments = entry.get("arguments", {})
                if isinstance(name, str) and name.strip() and isinstance(
                    arguments, dict
                ):
                    calls.append(
                        NativeToolCall(name=name.strip(), arguments=dict(arguments))
                    )
        return AIResponse(
            content=self._next_response(),
            model=self._model,
            provider=self.name,
            metadata={"mock": True, "native_tools": True, **self.metadata},
            tool_calls=tuple(calls),
        )

    def stream_chat(
        self,
        messages: Sequence[AIMessage],
    ) -> Iterable[str]:
        if self.fail:
            raise ConnectionError("Mock AI provider is configured to fail.")

        if self.delay:
            time.sleep(self.delay)

        content = self._next_response()

        for word in content.split(" "):
            yield word + " "
