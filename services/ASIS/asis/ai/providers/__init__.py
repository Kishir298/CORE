"""
A.S.I.S. AI providers.

``OllamaProvider`` is lazy: importing this package never requires
``requests`` (base install). The Ollama module is imported on first
attribute access; without the ``ai`` extra that raises an ImportError
naming the missing dependency.
"""

from __future__ import annotations

from typing import Any

from .base import AIProvider
from .mock import MockAIProvider

__all__ = ["AIProvider", "MockAIProvider", "OllamaProvider", "resolve_think"]


def __getattr__(name: str) -> Any:
    if name in ("OllamaProvider", "resolve_think"):
        try:
            from . import ollama as _ollama
        except ImportError as exc:
            raise ImportError(
                "OllamaProvider requires the 'requests' package "
                "(pip install -e '.[ai]')."
            ) from exc
        value = getattr(_ollama, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
