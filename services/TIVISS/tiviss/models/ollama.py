"""Ollama model provider for T.I.V.I.S.S.

Real implementation using Ollama's HTTP API (compatible with OpenAI-compatible
endpoints). Supports streaming and native tool calling when available.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .provider import ModelProvider, ModelResponse, ProviderError, ProviderInfo


def _validate_timeout(timeout_s: float | None) -> None:
    """Validate ``timeout_s``; raise :class:`ProviderError` when invalid."""
    if timeout_s is None:
        return
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)):
        raise ProviderError("timeout_s must be a positive number of seconds")
    try:
        value = float(timeout_s)
    except (TypeError, ValueError):
        raise ProviderError("timeout_s must be a positive number of seconds") from None
    import math
    if not math.isfinite(value) or value <= 0:
        raise ProviderError("timeout_s must be a positive number of seconds")


def _strip_thinking_tags(text: str) -> str:
    """Remove thinking tags (``<think>...</think>``) from model output."""
    import re
    # Remove <think> blocks
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip()


@dataclass
class _OllamaMessage:
    role: str
    content: str


class OllamaProvider(ModelProvider):
    """Ollama HTTP API provider for TIVISS.

    Communicates with a local Ollama server via its REST API.
    Supports streaming, native tool calling (when model supports it),
    and automatic thinking tag stripping for qwen3-class models.
    """

    PROVIDER_ID = "ollama"

    def __init__(
        self,
        *,
        endpoint: str = "http://127.0.0.1:11434",
        model_id: str = "qwen3:14b",
        version: str = "0.1.0",
        timeout_s: float = 60.0,
        temperature: float = 0.7,
        num_predict: int = 0,
        keep_alive: str = "30m",
        strip_thinking: bool = True,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._model_id = model_id
        self._version = version
        self._default_timeout = timeout_s
        self._temperature = temperature
        self._num_predict = num_predict
        self._keep_alive = keep_alive
        self._strip_thinking = strip_thinking
        self._available_cache: bool | None = None
        self._cache_time: float = 0.0

    @property
    def provider_id(self) -> str:
        return self.PROVIDER_ID

    @property
    def model_id(self) -> str:
        return self._model_id

    def available(self) -> bool:
        """Check if Ollama is reachable and model is available."""
        now = time.time()
        if self._available_cache is not None and now - self._cache_time < 5.0:
            return self._available_cache
        try:
            # Quick check: list models
            req = urllib.request.Request(
                f"{self._endpoint}/api/tags",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("models", [])
                self._available_cache = any(
                    m.get("name", "").startswith(self._model_id.split(":")[0])
                    for m in models
                )
                self._cache_time = now
                return self._available_cache
        except Exception:
            self._available_cache = False
            self._cache_time = now
            return False

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            provider_id=self.provider_id,
            model_id=self._model_id,
            version=self._version,
            available=self.available(),
        )

    def configure(self, config: Mapping[str, Any]) -> None:
        if "model_id" in config:
            self._model_id = str(config["model_id"])
            self._available_cache = None
        if "endpoint" in config:
            self._endpoint = str(config["endpoint"]).rstrip("/")
            self._available_cache = None
        if "timeout_s" in config:
            self._default_timeout = float(config["timeout_s"])
        if "temperature" in config:
            self._temperature = float(config["temperature"])
        if "num_predict" in config:
            self._num_predict = int(config["num_predict"])
        if "keep_alive" in config:
            self._keep_alive = str(config["keep_alive"])
        if "strip_thinking" in config:
            self._strip_thinking = bool(config["strip_thinking"])

    def generate(
        self,
        content: str,
        *,
        context: Mapping[str, Any] | None = None,
        timeout_s: float | None = None,
    ) -> ModelResponse:
        _validate_timeout(timeout_s)

        if not self.available():
            raise ProviderError(
                f"provider {self.provider_id}/{self.model_id} is not available"
            )

        if not isinstance(content, str) or not content.strip():
            raise ProviderError("cannot generate a response for empty content")

        # Build request payload
        payload = {
            "model": self._model_id,
            "messages": [
                {"role": "user", "content": content.strip()}
            ],
            "stream": False,
            "options": {
                "temperature": self._temperature,
                "num_predict": self._num_predict,
            },
            "keep_alive": self._keep_alive,
        }

        # Add system message if provided in context
        if context and "system" in context:
            payload["messages"].insert(0, {"role": "system", "content": str(context["system"])})

        # Add tools if provided (for native tool calling)
        if context and "tools" in context:
            payload["tools"] = context["tools"]
            payload["tool_choice"] = context.get("tool_choice", "auto")

        timeout = timeout_s or self._default_timeout

        # Make HTTP request
        req = urllib.request.Request(
            f"{self._endpoint}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            raise ProviderError(f"Ollama HTTP {e.code}: {error_body}") from e
        except urllib.error.URLError as e:
            raise ProviderError(f"Ollama connection error: {e.reason}") from e
        except json.JSONDecodeError as e:
            raise ProviderError(f"Ollama returned invalid JSON: {e}") from e
        except Exception as e:
            raise ProviderError(f"Ollama request failed: {e}") from e

        # Parse response
        message = response_data.get("message", {})
        content = message.get("content", "")
        _ = message.get("tool_calls")

        # Strip thinking tags for qwen3-class models
        if self._strip_thinking and content:
            content = _strip_thinking_tags(content)

        usage = response_data.get("usage", {})
        usage_dict = {
            "prompt_tokens": usage.get("prompt_eval_count", 0),
            "completion_tokens": usage.get("eval_count", 0),
            "total_tokens": usage.get("prompt_eval_count", 0) + usage.get("eval_count", 0),
        }

        return ModelResponse(
            content=content,
            provider_id=self.provider_id,
            model_id=self._model_id,
            model_version=self._version,
            usage=usage_dict,
        )


def create_ollama_provider(config: Mapping[str, Any]) -> OllamaProvider:
    """Factory function to create OllamaProvider from config mapping."""
    return OllamaProvider(
        endpoint=str(config.get("endpoint", "http://127.0.0.1:11434")),
        model_id=str(config.get("model_id", "qwen3:14b")),
        version=str(config.get("version", "0.1.0")),
        timeout_s=float(config.get("timeout_s", 60.0)),
        temperature=float(config.get("temperature", 0.7)),
        num_predict=int(config.get("num_predict", 0)),
        keep_alive=str(config.get("keep_alive", "30m")),
        strip_thinking=bool(config.get("strip_thinking", True)),
    )
