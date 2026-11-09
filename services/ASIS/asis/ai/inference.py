"""
Inference orchestration for A.S.I.S.

Combines the AI provider, context assembler and interrupt coordinator
into a single inference pipeline. Cancellation is cooperative: a cancel
requested through the ``inference`` scope raises CancellationError at
the next chunk boundary.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from asis.errors import CancellationError
from asis.logging.logger import get_logger
from asis.system.interrupt import InterruptCoordinator

from .context import ContextAssembler
from .manager import AIManager
from .models import AIMessage, AIResponse

_INFERENCE_SCOPE = "inference"


class InferenceEngine:
    """Runs model responses through context assembly."""

    def __init__(
        self,
        manager: AIManager,
        assembler: ContextAssembler,
        interrupts: InterruptCoordinator | None = None,
    ) -> None:
        self.manager = manager
        self.assembler = assembler
        self.interrupts = interrupts
        self.logger = get_logger("ai.inference")

    def _await_cancellation(self) -> None:
        if self.interrupts is None:
            return

        self.interrupts.check(_INFERENCE_SCOPE)

    def reset_turn(self) -> None:
        """Reset cancellation for a new user turn (call at turn boundary).

        The engine itself never resets implicitly: a cancel issued before
        generation must still abort (see test_cancellation_propagates).
        The interactive loop calls this when starting a fresh prompt so one
        ESC never poisons the next request.
        """
        if self.interrupts is None:
            return
        import contextlib

        with contextlib.suppress(Exception):
            self.interrupts.register(_INFERENCE_SCOPE)

    def generate(
        self,
        history: Sequence[AIMessage],
    ) -> AIResponse:
        """Generate a full non-streaming response."""
        self._await_cancellation()

        messages = self.assembler.build_messages(history)
        response = self.manager.chat(messages)

        self._await_cancellation()
        return response

    def generate_with_tools(
        self,
        history: Sequence[AIMessage],
        tools: Sequence[Any],
    ) -> AIResponse:
        """Generate a response with native tool definitions attached."""
        self._await_cancellation()

        messages = self.assembler.build_messages(history)
        response = self.manager.chat_with_tools(messages, tools)

        self._await_cancellation()
        return response

    def generate_and_stream(
        self,
        history: Sequence[AIMessage],
    ):
        """Generate a response while yielding text chunks."""
        self._await_cancellation()

        messages = self.assembler.build_messages(history)

        parts: list[str] = []

        for chunk in self.manager.stream_chat(messages):
            self._await_cancellation()
            parts.append(chunk)
            yield chunk

        if not parts:
            raise CancellationError("Response cancelled before content arrived.")

    def generate_streamed(
        self,
        history: Sequence[AIMessage],
        on_chunk=None,
    ) -> str:
        """Stream chunks to ``on_chunk`` as they arrive; return full text.

        True streaming path for the CLI: Ollama chunk -> provider ->
        engine -> caller/terminal without waiting for completion.
        ``on_chunk`` is best-effort (never breaks generation).
        """
        self._await_cancellation()

        messages = self.assembler.build_messages(history)
        parts: list[str] = []

        for chunk in self.manager.stream_chat(messages):
            self._await_cancellation()
            if chunk:
                parts.append(chunk)
                if on_chunk is not None:
                    import contextlib

                    with contextlib.suppress(Exception):
                        on_chunk(chunk)

        if not parts:
            raise CancellationError("Response cancelled before content arrived.")
        self._await_cancellation()
        return "".join(parts)

    def cancel_current(self) -> None:
        """Request cancellation of the active response."""
        if self.interrupts is None:
            return

        self.interrupts.cancel(_INFERENCE_SCOPE)
        self.logger.info("Inference cancellation requested.")
