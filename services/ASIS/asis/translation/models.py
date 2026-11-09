"""
Translation result models.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranslationResult:
    """Structured outcome of a translation request (data, never action)."""

    source_language: str
    target_language: str
    source_text: str
    translated_text: str
    provider: str
    model: str
    detected_source: bool = False
    cached: bool = False
