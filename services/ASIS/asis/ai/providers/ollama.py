"""
Ollama AI provider for A.S.I.S.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Any

from asis.configuration.defaults import AI_MODEL as DEFAULT_OLLAMA_MODEL
from asis.errors import InferenceError

from ..models import AIMessage, AIResponse, NativeToolCall
from .base import AIProvider

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    import requests


def _requests():
    """Import ``requests`` lazily so base installs work without it.

    The Ollama provider is optional (``requirements/ai.txt``); importing
    this module must never fail on a minimal install. Actual HTTP use
    raises a clear error when the package is missing.
    """
    try:
        import requests
    except ImportError as exc:
        raise InferenceError(
            "The 'requests' package is required for the Ollama provider "
            "(pip install requests)."
        ) from exc
    return requests

# Upper bound for the implicit availability probe so a down/unreachable
# server is reported fast. Inference timeouts are unaffected; callers may
# still pass an explicit ``timeout`` to ``available()``.
AVAILABILITY_PROBE_TIMEOUT = 5.0

_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"


def strip_thinking(content: str) -> tuple[str, str]:
    """Split qwen3-style thinking from user-visible content.

    Returns ``(visible, thinking)``. Handles ``<think>...</think>``
    blocks (case-insensitive) and unclosed blocks (rest is thinking).
    Private reasoning is never part of ``visible``.
    """
    import re as _re

    text = content or ""
    thinking_parts: list[str] = []

    pattern = _re.compile(r"<think\s*>.*?(</think\s*>|$)", _re.IGNORECASE | _re.DOTALL)
    pos = 0
    visible_parts: list[str] = []
    for match in pattern.finditer(text):
        visible_parts.append(text[pos : match.start()])
        thinking_parts.append(match.group(0))
        pos = match.end()
    visible_parts.append(text[pos:])
    visible = "".join(visible_parts).strip()
    thinking = "".join(thinking_parts).strip()
    # Drop stray unpaired markers (e.g. a lone </think> with no opener):
    # with thinking disabled these are always model artifacts, never
    # legitimate content, and must not reach the terminal (live 2026-09-18:
    # qwen3:14b emitted a bare </think> around a tool-turn answer).
    visible = _re.sub(r"</?think\s*>", "", visible, flags=_re.IGNORECASE).strip()
    return visible, thinking


class _ThinkingStreamFilter:
    """Incremental filter so streamed thinking never reaches the terminal."""

    def __init__(self) -> None:
        self._in_think = False
        self._buf = ""

    def feed(self, chunk: str) -> str:
        """Return only the user-visible portion of ``chunk``."""
        text = f"{self._buf}{chunk or ''}"
        self._buf = ""
        out: list[str] = []
        lowered_tag_open = _THINK_OPEN
        lowered_tag_close = _THINK_CLOSE
        while text:
            low = text.lower()
            if not self._in_think:
                idx = low.find(lowered_tag_open)
                if idx == -1:
                    # Keep a tail that could be a split "<think" prefix.
                    keep = _split_prefix_tail(text)
                    if keep < len(text):
                        out.append(text[:keep])
                        self._buf = text[keep:]
                        text = ""
                    else:
                        out.append(text)
                        text = ""
                else:
                    out.append(text[:idx])
                    text = text[idx + len(lowered_tag_open) :]
                    self._in_think = True
            else:
                idx = low.find(lowered_tag_close)
                if idx == -1:
                    keep = _split_prefix_tail(text, closing=True)
                    if keep < len(text):
                        self._buf = text[keep:]
                    # All thinking so far: emit nothing.
                    text = ""
                else:
                    text = text[idx + len(lowered_tag_close) :]
                    self._in_think = False
        # Drop stray unpaired markers outside thinking spans (same live
        # artifact as strip_thinking: a bare </think> with no opener).
        # Split-tag tails are held in _buf, never in out, so this is safe.
        import re as _re_filter

        return _re_filter.sub(
            r"</?think\s*>", "", "".join(out), flags=_re_filter.IGNORECASE
        )


def _split_prefix_tail(text: str, closing: bool = False) -> int:
    """Return safe-emit length, holding back a possible split tag tail."""
    tags = ("</think>", "<think>") if not closing else ("</think>",)
    low = text.lower()
    # Hold back up to len("</think>")-1 chars that could complete a tag.
    hold = max(1, len("</think>") - 1)
    tail = low[max(0, len(low) - hold - 1) :]
    for tag in tags:
        for i in range(1, min(len(tail), len(tag)) + 1):
            if tag.startswith(tail[-i:]):
                return len(text) - i
    # Also hold a bare "<" tail that could start a tag.
    if "<" in tail:
        return text.rfind("<")
    return len(text)


_THINKING_MODEL_HINTS = ("qwen3", "deepseek-r1", "deepseek-r1:", "r1-", "gpt-oss")


def resolve_think(mode: str, model: str) -> bool | None:
    """Resolve the ``ASIS_AI_THINK`` setting to an Ollama ``think`` value.

    ``true``/``false`` force the flag; ``auto`` (default) disables thinking
    only for known thinking-model families and leaves the parameter unset
    otherwise (older servers ignore unknown fields, but explicit minimal
    payloads stay safest). Returns None when the flag must be omitted.
    """
    normalized = (mode or "auto").strip().lower()
    if normalized in ("true", "1", "yes", "on", "enabled"):
        return True
    if normalized in ("false", "0", "no", "off", "disabled"):
        return False
    lowered_model = (model or "").lower()
    if any(hint in lowered_model for hint in _THINKING_MODEL_HINTS):
        return False
    return None


class OllamaProvider(AIProvider):
    """AI provider backed by a local Ollama server."""

    def __init__(
        self,
        model: str = DEFAULT_OLLAMA_MODEL,
        host: str = "http://127.0.0.1:11434",
        timeout: float = 120.0,
        temperature: float | None = None,
        request_timeout: float | None = None,
        retries: int = 0,
        think: bool | None = None,
        num_predict: int | None = None,
        keep_alive: str | None = None,
    ) -> None:
        self._model = model
        self.host = host.rstrip("/")
        # Explicit timeout wins; request_timeout mirrors settings naming.
        self.timeout = timeout if request_timeout is None else request_timeout
        self.temperature = temperature
        self.retries = max(0, int(retries))
        self.think = think
        self.num_predict = num_predict
        self.keep_alive = (keep_alive or "").strip() or None

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def model(self) -> str:
        return self._model

    def available(self, timeout: float | None = None) -> bool:
        """Return True when the Ollama server is reachable.

        The implicit probe is capped at ``AVAILABILITY_PROBE_TIMEOUT``
        seconds so offline/down servers report fast instead of blocking
        on the (long) inference timeout.
        """
        if timeout is None:
            probe = min(float(self.timeout), AVAILABILITY_PROBE_TIMEOUT)
        else:
            probe = timeout
        try:
            requests = _requests()
        except InferenceError:
            return False
        try:
            response = requests.get(
                f"{self.host}/api/tags",
                timeout=probe,
            )
            return response.ok

        except requests.RequestException:
            return False

    def _payload(
        self,
        messages: Sequence[AIMessage],
        *,
        stream: bool,
        tools: Sequence[dict] | None = None,
    ) -> dict:
        payload: dict = {
            "model": self._model,
            "messages": [
                {
                    "role": message.role.value,
                    "content": message.content,
                }
                for message in messages
            ],
            "stream": stream,
        }
        if self.temperature is not None:
            payload["options"] = {"temperature": self.temperature}
        if self.num_predict:
            payload.setdefault("options", {})["num_predict"] = self.num_predict
        if self.think is not None:
            # Top-level only: `think` inside `options` is silently ignored.
            payload["think"] = self.think
        if self.keep_alive:
            payload["keep_alive"] = self.keep_alive
        if tools:
            payload["tools"] = list(tools)
        return payload

    def _communication_error(self, exc: Exception) -> InferenceError:
        return InferenceError(f"Could not communicate with Ollama: {exc}")

    def chat(
        self,
        messages: Sequence[AIMessage],
    ) -> AIResponse:
        """Send a non-streaming chat request (retried per configuration)."""
        requests = _requests()
        attempts = 1 + self.retries
        for attempt in range(attempts):
            try:
                response = requests.post(
                    f"{self.host}/api/chat",
                    json=self._payload(messages, stream=False),
                    timeout=self.timeout,
                )
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                if attempt + 1 >= attempts:
                    raise self._communication_error(exc) from exc

        data = response.json()
        message = data.get("message") or {}
        content = message.get("content")
        thinking_field = message.get("thinking") or message.get("reasoning") or ""

        if not isinstance(content, str):
            raise InferenceError("Ollama returned an invalid response.")
        if thinking_field and not isinstance(thinking_field, str):
            thinking_field = str(thinking_field)

        visible, thinking = strip_thinking(content)
        combined_thinking = "\n".join(
            part for part in (str(thinking_field or "").strip(), thinking) if part
        )

        return AIResponse(
            content=visible,
            model=self._model,
            provider=self.name,
            metadata={
                "done": data.get("done"),
                "total_duration": data.get("total_duration"),
                "prompt_eval_count": data.get("prompt_eval_count"),
                "eval_count": data.get("eval_count"),
                "thinking": combined_thinking,
            },
        )

    @property
    def supports_native_tools(self) -> bool:
        """Ollama's /api/chat accepts a tools array (model-dependent)."""
        return True

    @staticmethod
    def parse_tool_calls(message: dict) -> tuple[NativeToolCall, ...]:
        """Extract valid native calls; drop malformed entries safely."""
        raw_calls = message.get("tool_calls") or []
        if not isinstance(raw_calls, list):
            return ()
        parsed: list[NativeToolCall] = []
        for entry in raw_calls:
            if not isinstance(entry, dict):
                continue
            function = entry.get("function")
            if not isinstance(function, dict):
                continue
            name = function.get("name")
            arguments = function.get("arguments", {})
            if arguments is None:
                arguments = {}
            if not isinstance(name, str) or not name.strip():
                continue
            if not isinstance(arguments, dict):
                continue
            try:
                parsed.append(
                    NativeToolCall(name=name.strip(), arguments=dict(arguments))
                )
            except TypeError:
                continue
        return tuple(parsed)

    def chat_with_tools(
        self,
        messages: Sequence[AIMessage],
        tools: Sequence[Any],
    ) -> AIResponse:
        """Send a non-streaming chat request with tool definitions."""
        from asis.ai.tool_schemas import ollama_tools

        requests = _requests()
        wire = ollama_tools(list(tools))
        attempts = 1 + self.retries
        for attempt in range(attempts):
            try:
                response = requests.post(
                    f"{self.host}/api/chat",
                    json=self._payload(messages, stream=False, tools=wire),
                    timeout=self.timeout,
                )
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                if attempt + 1 >= attempts:
                    raise self._communication_error(exc) from exc

        data = response.json()
        message = data.get("message") or {}
        content = message.get("content")
        thinking_field = message.get("thinking") or message.get("reasoning") or ""
        if content is None:
            content = ""
        if not isinstance(content, str):
            raise InferenceError("Ollama returned an invalid response.")
        if thinking_field and not isinstance(thinking_field, str):
            thinking_field = str(thinking_field)

        visible, thinking = strip_thinking(content)
        combined_thinking = "\n".join(
            part for part in (str(thinking_field or "").strip(), thinking) if part
        )

        return AIResponse(
            content=visible,
            model=self._model,
            provider=self.name,
            metadata={
                "done": data.get("done"),
                "total_duration": data.get("total_duration"),
                "prompt_eval_count": data.get("prompt_eval_count"),
                "eval_count": data.get("eval_count"),
                "native_tools": True,
                "thinking": combined_thinking,
            },
            tool_calls=self.parse_tool_calls(message),
        )

    def stream_chat(
        self,
        messages: Sequence[AIMessage],
    ) -> Iterator[str]:
        """
        Stream generated text from Ollama.

        Each yielded value is a newly generated text chunk.

        KeyboardInterrupt is intentionally allowed to propagate to the
        caller so Ctrl+C can interrupt the current response.
        """
        requests = _requests()
        response: requests.Response | None = None

        try:
            response = requests.post(
                f"{self.host}/api/chat",
                json=self._payload(messages, stream=True),
                stream=True,
                timeout=self.timeout,
            )
            response.raise_for_status()
            thinking_filter = _ThinkingStreamFilter()

            for line in response.iter_lines(
                decode_unicode=True,
            ):
                if not line:
                    continue

                try:
                    data = json.loads(line)

                except json.JSONDecodeError as exc:
                    raise InferenceError(
                        "Ollama returned invalid streaming data."
                    ) from exc

                message = data.get("message") or {}
                content = message.get("content", "")

                if content:
                    visible = thinking_filter.feed(content)
                    if visible:
                        yield visible

                if data.get("done"):
                    # Flush any buffered visible tail (never thinking).
                    tail = thinking_filter.feed("")
                    if tail:
                        yield tail
                    break

        except requests.RequestException as exc:
            raise self._communication_error(exc) from exc

        finally:
            if response is not None:
                response.close()
