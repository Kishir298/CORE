"""Model provider abstraction.

T.I.V.I.S.S. is not hard-coded to a single AI model. Providers implement this
interface and can be swapped (local mock today, a real provider later).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


class ProviderError(RuntimeError):
    """Raised when a provider cannot fulfill a generation request."""


@dataclass(frozen=True)
class ProviderInfo:
    """Static facts about a provider and its model."""

    provider_id: str
    model_id: str
    version: str
    available: bool


@dataclass(frozen=True)
class ModelResponse:
    """A single generated response from a provider."""

    content: str
    provider_id: str
    model_id: str
    model_version: str | None = None
    usage: Mapping[str, Any] = field(default_factory=dict)


class ModelProvider(ABC):
    """Interface to an AI model."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Stable identifier for this provider."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Identifier of the currently selected model."""

    @abstractmethod
    def available(self) -> bool:
        """Whether the provider is reachable and usable."""

    @abstractmethod
    def info(self) -> ProviderInfo:
        """Describe the provider and model."""

    @abstractmethod
    def configure(self, config: Mapping[str, Any]) -> None:
        """Apply provider-specific configuration (optional)."""

    @abstractmethod
    def generate(
        self,
        content: str,
        *,
        context: Mapping[str, Any] | None = None,
        timeout_s: float | None = None,
    ) -> ModelResponse:
        """Generate a model response for ``content``.

        ``timeout_s`` is an optional per-request timeout in seconds. When
        given it must be a positive, finite number; zero, negative, NaN,
        infinite, or non-numeric values are rejected with
        :class:`ProviderError`. ``None`` (the default) means no timeout.

        Raises :class:`ProviderError` on failure.
        """
