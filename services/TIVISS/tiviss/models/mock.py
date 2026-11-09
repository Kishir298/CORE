"""Deterministic mock model provider for development and tests.

The mock follows a fixed, deterministic transformation of its input so tests
and integration tests are repeatable without any external model service.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .provider import ModelProvider, ModelResponse, ProviderError, ProviderInfo


def _to_bool(raw: Any, default: bool = False) -> bool:
    """Strict bool parse (mirrors config._to_bool): bool passthrough,
    None -> default, else string in {"1","true","yes","on"}.

    Avoids the ``bool("false") is True`` pitfall.
    """
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


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


class MockProvider(ModelProvider):
    """Local provider with deterministic output.

    ``failure_mode`` simulates an unavailable/broken provider for tests.
    """

    PROVIDER_ID = "mock.local"

    def __init__(
        self,
        *,
        model_id: str = "tiviss-mock-1",
        version: str = "0.1.0",
        prefix: str = "ack",
        failure_mode: bool = False,
    ) -> None:
        self._model_id = model_id
        self._version = version
        self._prefix = prefix
        self._failure_mode = _to_bool(failure_mode, False)

    @property
    def provider_id(self) -> str:
        return self.PROVIDER_ID

    @property
    def model_id(self) -> str:
        return self._model_id

    def available(self) -> bool:
        return not self._failure_mode

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            provider_id=self.provider_id,
            model_id=self.model_id,
            version=self._version,
            available=self.available(),
        )

    def configure(self, config: Mapping[str, Any]) -> None:
        if "failure_mode" in config:
            self._failure_mode = _to_bool(config["failure_mode"], self._failure_mode)
        if "prefix" in config:
            self._prefix = str(config["prefix"])
        if "model_id" in config:
            self._model_id = str(config["model_id"])

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

        context = dict(context or {})
        echoed = content.strip()
        if "wordlimit" in context:
            raw_limit = context["wordlimit"]
            if isinstance(raw_limit, bool) or not isinstance(raw_limit, (int, str)):
                raise ProviderError("invalid wordlimit in context")
            try:
                limit = int(raw_limit)
            except (TypeError, ValueError):
                raise ProviderError("invalid wordlimit in context") from None
            if limit < 0:
                raise ProviderError("invalid wordlimit in context")
            echoed = " ".join(echoed.split()[:limit])

        return ModelResponse(
            content=f"{self._prefix}({self.model_id}): {echoed}",
            provider_id=self.provider_id,
            model_id=self.model_id,
            model_version=self._version,
            usage={"mock": True, "echoed_chars": len(echoed)},
        )
