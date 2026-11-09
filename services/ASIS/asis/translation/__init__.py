"""
A.S.I.S. offline Translation Engine.

Local multilingual translation with provider abstraction, language
registry, offline detection, bounded caching, and safety controls.
Runtime never requires internet and never downloads models.
"""

from asis.translation.cache import TranslationCache
from asis.translation.detection import DetectionResult, detect_language
from asis.translation.engine import TranslationEngine
from asis.translation.errors import TranslationError
from asis.translation.languages import (
    Language,
    get_language,
    is_speech_input_supported,
    is_speech_output_supported,
    is_supported,
    normalize_code,
    supported_languages,
)
from asis.translation.models import TranslationResult
from asis.translation.provider import (
    MADLAD_LICENSE,
    MADLAD_MODEL_ID,
    MadladProvider,
    MockTranslationProvider,
    TranslationProvider,
    TranslationProviderError,
    build_provider,
)
from asis.translation.voice import (
    speak_translation,
    speech_to_speech_translation,
    speech_to_text_translation,
    text_to_speech_translation,
    translate_speech,
)

__all__ = [
    "TranslationCache",
    "DetectionResult",
    "detect_language",
    "TranslationEngine",
    "TranslationError",
    "Language",
    "get_language",
    "is_speech_input_supported",
    "is_speech_output_supported",
    "is_supported",
    "normalize_code",
    "supported_languages",
    "TranslationResult",
    "MADLAD_LICENSE",
    "MADLAD_MODEL_ID",
    "MadladProvider",
    "MockTranslationProvider",
    "TranslationProvider",
    "TranslationProviderError",
    "build_provider",
    "speech_to_speech_translation",
    "speech_to_text_translation",
    "speak_translation",
    "text_to_speech_translation",
    "translate_speech",
]
