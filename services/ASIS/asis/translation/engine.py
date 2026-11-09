"""
A.S.I.S. Translation Engine: local multilingual translation.

Orchestrates registry validation, offline language detection, span
protection (URLs, paths, code), provider inference, and bounded caching.
The engine never touches the network; providers are local-only and the
runtime never downloads models.
"""

from __future__ import annotations

import re

from asis.translation import errors
from asis.translation.cache import TranslationCache
from asis.translation.detection import DetectionResult, detect_language
from asis.translation.languages import (
    Language,
    is_supported,
    normalize_code,
    supported_languages,
)
from asis.translation.models import TranslationResult
from asis.translation.provider import (
    MockTranslationProvider,
    TranslationProvider,
    TranslationProviderError,
    build_provider,
)

DEFAULT_MAX_CHARS = 5_000

# Spans that must survive translation verbatim unless the caller opts out.
_URL = re.compile(r"https?://[^\s<>\"]+|www\.[^\s<>\"]+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PATH = re.compile(r"(?<![\w.])(?:/[A-Za-z0-9_][\w.+-]*)+(?:/[\w.+-]*)*")
_CODE = re.compile(r"`[^`]+`")

_BEGIN = "\ue000"
_END = "\ue001"


class TranslationEngine:
    """Local translation entry point owned by A.S.I.S."""

    def __init__(
        self,
        provider: TranslationProvider | None = None,
        cache: TranslationCache | None = None,
        max_chars: int = DEFAULT_MAX_CHARS,
    ) -> None:
        self._provider = provider if provider is not None else MockTranslationProvider()
        self._cache = cache if cache is not None else TranslationCache()
        self._max_chars = max(1, int(max_chars))

    @property
    def provider(self) -> TranslationProvider:
        return self._provider

    @property
    def provider_name(self) -> str:
        return self._provider.name

    # -- capability API --------------------------------------------------
    def supported_languages(self) -> list[Language]:
        return supported_languages()

    def is_language_supported(self, code: str) -> bool:
        return is_supported(code)

    def detect_language(self, text: str) -> DetectionResult:
        return detect_language(text)

    # -- span protection ---------------------------------------------------
    @staticmethod
    def protect_spans(text: str) -> tuple[str, list[str]]:
        """Replace URLs/paths/code with placeholders; return (masked, spans)."""
        spans: list[str] = []

        def _stash(match: re.Match) -> str:
            spans.append(match.group(0))
            return f"{_BEGIN}{len(spans) - 1}{_END}"

        masked = text
        for pattern in (_CODE, _URL, _EMAIL, _PATH):
            masked = pattern.sub(_stash, masked)
        return masked, spans

    @staticmethod
    def restore_spans(text: str, spans: list[str]) -> str:
        """Restore protected spans into translated ``text``."""
        def _unstash(match: re.Match) -> str:
            try:
                return spans[int(match.group(1))]
            except (ValueError, IndexError):
                return match.group(0)

        return re.sub(f"{_BEGIN}(\\d+){_END}", _unstash, text)

    # -- translation ---------------------------------------------------------
    def translate_text(
        self,
        text: str,
        target: str,
        source: str | None = None,
        *,
        protect: bool = True,
    ) -> TranslationResult:
        """Translate ``text`` into ``target`` (registry codes).

        ``source`` may be omitted or ``"auto"`` to trigger offline
        detection; uncertain detection raises ``LANGUAGE_DETECTION_FAILED``
        instead of guessing. Set ``protect=False`` to translate protected
        spans (code, paths, URLs) too.
        """
        if not isinstance(text, str) or not text.strip():
            raise errors.invalid_input("'text' must be a non-empty string.")
        cleaned = text.strip()
        if len(cleaned) > self._max_chars:
            raise errors.too_large(self._max_chars)

        target_code = normalize_code(target or "")
        if target_code is None:
            raise errors.unsupported_language(str(target))

        detected = False
        auto = source is None or (
            isinstance(source, str) and source.strip().lower() == "auto"
        )
        if auto:
            result = detect_language(cleaned)
            if result.language is None or result.uncertain:
                raise errors.detection_failed()
            source_code = result.language
            detected = True
        else:
            source_code = normalize_code(source)
            if source_code is None:
                raise errors.unsupported_language(str(source))

        if source_code == target_code:
            return TranslationResult(
                source_language=source_code,
                target_language=target_code,
                source_text=cleaned,
                translated_text=cleaned,
                provider=self._provider.name,
                model=self._provider.model_id,
                detected_source=detected,
                cached=False,
            )

        cached = self._cache.get(cleaned, source_code, target_code)
        if cached is not None:
            return TranslationResult(
                source_language=source_code,
                target_language=target_code,
                source_text=cleaned,
                translated_text=cached,
                provider=self._provider.name,
                model=self._provider.model_id,
                detected_source=detected,
                cached=True,
            )

        if protect:
            masked, spans = self.protect_spans(cleaned)
        else:
            masked, spans = cleaned, []
        try:
            raw = self._provider.translate(masked, source_code, target_code)
        except TranslationProviderError as exc:
            code = exc.code or "TRANSLATION_PROVIDER_ERROR"
            if code == "TRANSLATION_MODEL_NOT_INSTALLED":
                raise errors.model_not_installed(exc.message) from exc
            raise errors.provider_error(
                exc.message.split(": ", 1)[-1] if ": " in exc.message else exc.message
            ) from exc
        translated = self.restore_spans(raw, spans) if protect else raw
        self._cache.put(cleaned, source_code, target_code, translated)
        return TranslationResult(
            source_language=source_code,
            target_language=target_code,
            source_text=cleaned,
            translated_text=translated,
            provider=self._provider.name,
            model=self._provider.model_id,
            detected_source=detected,
            cached=False,
        )


def build_engine_from_settings(settings_obj=None) -> TranslationEngine:
    """Build the configured engine (provider + cache + input limit)."""
    if settings_obj is None:
        from asis.configuration.settings import settings as settings_obj
    web = settings_obj.translation
    provider = build_provider(
        web.provider, model_path=web.model_path, device=web.device
    )
    cache = TranslationCache(
        max_size=web.cache_size, enabled=web.cache_enabled
    )
    return TranslationEngine(provider=provider, cache=cache, max_chars=web.max_chars)
