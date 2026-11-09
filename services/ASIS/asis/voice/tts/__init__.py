"""
TTS providers.
"""

try:  # optional heavy dep; never break base imports
    from .pyttsx3_engine import Pyttsx3Engine
except Exception:  # pragma: no cover - missing optional dep
    Pyttsx3Engine = None  # type: ignore[assignment]

__all__ = ["Pyttsx3Engine"]
