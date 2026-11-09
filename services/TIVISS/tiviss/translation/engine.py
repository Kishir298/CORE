"""Translation engine for T.I.V.I.S.S.

Provides offline translation using a simple dictionary-based approach
or structured unavailable results for unavailable languages.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..configuration import settings as tiviss_settings
from ..errors import ErrorCode, TivissError


@dataclass
class TranslateResult:
    """Structured result of a translation."""
    source_language: str
    target_language: str
    source_text: str
    translated_text: str
    provider: str
    model: str
    detected_source: str | None
    cached: bool


class TranslationError(TivissError):
    """Translation-specific error."""
    pass


class TranslationEngine:
    """Local translation engine with offline/mock implementation."""

    def __init__(self):
        self._settings = tiviss_settings.translation
        # Simple mock translations for common phrases
        self._mock_translations = {
            ("en", "es"): {
                "hello": "hola",
                "world": "mundo",
                "hello world": "hola mundo",
                "good morning": "buenos días",
                "good night": "buenas noches",
                "thank you": "gracias",
                "yes": "sí",
                "no": "no",
            },
            ("es", "en"): {
                "hola": "hello",
                "mundo": "world",
                "hola mundo": "hello world",
                "buenos días": "good morning",
                "buenas noches": "good night",
                "gracias": "thank you",
                "sí": "yes",
                "no": "no",
            },
            ("en", "fr"): {
                "hello": "bonjour",
                "world": "monde",
                "hello world": "bonjour le monde",
                "good morning": "bonjour",
                "good night": "bonne nuit",
                "thank you": "merci",
                "yes": "oui",
                "no": "non",
            },
            ("fr", "en"): {
                "bonjour": "hello",
                "monde": "world",
                "bonjour le monde": "hello world",
                "bonne nuit": "good night",
                "merci": "thank you",
                "oui": "yes",
                "non": "no",
            },
            ("en", "de"): {
                "hello": "hallo",
                "world": "welt",
                "hello world": "hallo welt",
                "good morning": "guten morgen",
                "good night": "gute nacht",
                "thank you": "danke",
                "yes": "ja",
                "no": "nein",
            },
            ("de", "en"): {
                "hallo": "hello",
                "welt": "world",
                "hallo welt": "hello world",
                "guten morgen": "good morning",
                "gute nacht": "good night",
                "danke": "thank you",
                "ja": "yes",
                "nein": "no",
            },
        }

    def translate_text(
        self,
        text: str,
        target_language: str,
        source_language: str = "auto"
    ) -> TranslateResult:
        """Translate text to target language."""
        if not text.strip():
            raise TranslationError(ErrorCode.TRANSLATION_PROVIDER_ERROR, "Empty text")

        # Normalize language codes
        source = source_language.lower().strip()
        target = target_language.lower().strip()

        # Auto-detect source language (simple heuristic)
        if source == "auto":
            source = self._detect_language(text)

        # Check if translation is available
        key = (source, target)
        if key not in self._mock_translations:
            # Return structured unavailable result instead of claiming implementation
            return TranslateResult(
                source_language=source,
                target_language=target,
                source_text=text,
                translated_text=f"[Translation from {source} to {target} not available in offline mode]",
                provider="offline",
                model="mock-dictionary",
                detected_source=source if source != "auto" else None,
                cached=False,
            )

        # Simple word-by-word translation
        translations = self._mock_translations[key]
        words = text.lower().split()
        translated_words = [translations.get(w, w) for w in words]
        translated_text = " ".join(translated_words)

        # Check if it's an exact phrase match
        if text.lower() in translations:
            translated_text = translations[text.lower()]

        return TranslateResult(
            source_language=source,
            target_language=target,
            source_text=text,
            translated_text=translated_text,
            provider="offline",
            model="mock-dictionary",
            detected_source=source if source != "auto" else None,
            cached=False,
        )

    def _detect_language(self, text: str) -> str:
        """Simple language detection based on common words."""
        text_lower = text.lower()

        # Check for Spanish
        spanish_words = {"hola", "mundo", "gracias", "sí", "no", "buenos", "días", "noches"}
        if any(w in text_lower for w in spanish_words):
            return "es"

        # Check for French
        french_words = {"bonjour", "monde", "merci", "oui", "non", "bonne", "nuit"}
        if any(w in text_lower for w in french_words):
            return "fr"

        # Check for German
        german_words = {"hallo", "welt", "danke", "ja", "nein", "guten", "morgen", "nacht"}
        if any(w in text_lower for w in german_words):
            return "de"

        # Default to English
        return "en"


def build_engine_from_settings() -> TranslationEngine:
    """Build translation engine from settings."""
    return TranslationEngine()