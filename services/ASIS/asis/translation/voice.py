"""
Voice translation bridge: STT -> Translation Engine -> TTS.

Reuses the existing voice abstractions (no second speech stack):
transcription text flows into the shared TranslationEngine, and the
result flows into the shared TTS provider. Text, speech-input, and
speech-output support are checked separately and honestly — a language
may translate as text without being speakable.
"""

from __future__ import annotations

from asis.translation import errors
from asis.translation.engine import TranslationEngine
from asis.translation.languages import (
    is_speech_input_supported,
    is_speech_output_supported,
    normalize_code,
)
from asis.translation.models import TranslationResult


def translate_speech(
    text: str,
    target: str,
    *,
    stt_language: str | None = None,
    engine: TranslationEngine | None = None,
) -> TranslationResult:
    """Translate transcribed speech text into ``target``.

    ``stt_language`` is the STT-detected language when available; an
    explicit caller source is not taken here (use the engine directly).
    Falls back to offline auto-detection when the STT language is absent
    or unmapped.
    """
    active = engine if engine is not None else TranslationEngine()
    source: str | None = None
    if stt_language:
        mapped = normalize_code(stt_language)
        if mapped is None:
            raise errors.TranslationError(
                "STT_LANGUAGE_UNSUPPORTED",
                "STT_LANGUAGE_UNSUPPORTED: "
                f"'{stt_language}' is not a supported translation language.",
            )
        if not is_speech_input_supported(mapped):
            raise errors.TranslationError(
                "STT_LANGUAGE_UNSUPPORTED",
                "STT_LANGUAGE_UNSUPPORTED: speech input is not supported "
                f"for '{mapped}'.",
            )
        source = mapped
    return active.translate_text(text, target, source)


def speak_translation(
    translated_text: str,
    target: str,
    tts,
    *,
    check_support: bool = True,
):
    """Speak already-translated text via a TTS provider (offline)."""
    code = normalize_code(target or "")
    if code is None:
        raise errors.unsupported_language(str(target))
    if check_support and not is_speech_output_supported(code):
        raise errors.TranslationError(
            "TTS_LANGUAGE_UNSUPPORTED",
            "TTS_LANGUAGE_UNSUPPORTED: speech output is not supported "
            f"for '{code}' on this host.",
        )
    return tts.synthesize(translated_text)


def speech_to_text_translation(
    text: str,
    target: str,
    *,
    stt_language: str | None = None,
    engine: TranslationEngine | None = None,
) -> TranslationResult:
    """Speech -> text translation (STT output text in, translated text out)."""
    return translate_speech(text, target, stt_language=stt_language, engine=engine)


def speech_to_speech_translation(
    text: str,
    target: str,
    tts,
    *,
    stt_language: str | None = None,
    engine: TranslationEngine | None = None,
):
    """Speech -> speech translation (translated audio out via TTS)."""
    result = translate_speech(text, target, stt_language=stt_language, engine=engine)
    audio = speak_translation(result.translated_text, target, tts)
    return result, audio


def text_to_speech_translation(
    text: str,
    target: str,
    tts,
    *,
    source: str | None = None,
    engine: TranslationEngine | None = None,
):
    """Text -> speech translation (translated audio out via TTS)."""
    active = engine if engine is not None else TranslationEngine()
    result = active.translate_text(text, target, source)
    audio = speak_translation(result.translated_text, target, tts)
    return result, audio
