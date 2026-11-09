"""
Stable translation errors.

Every error carries a ``TRANSLATION_*``/``LANGUAGE_*``/``TTS/STT_*`` code
that is safe to surface to users and the model; messages never include
secrets or internal filesystem details.
"""

from __future__ import annotations


class TranslationError(Exception):
    """Translation failure with a stable code safe for user output."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def disabled() -> TranslationError:
    return TranslationError(
        "TRANSLATION_DISABLED",
        "TRANSLATION_DISABLED: translation is disabled by configuration.",
    )


def model_not_installed(detail: str = "") -> TranslationError:
    suffix = f" ({detail})" if detail else ""
    return TranslationError(
        "TRANSLATION_MODEL_NOT_INSTALLED",
        "TRANSLATION_MODEL_NOT_INSTALLED: no local translation model is "
        f"available{suffix}. Install MADLAD-400 3B MT while online "
        "(see docs/translation.md), or set ASIS_TRANSLATION_PROVIDER=mock.",
    )


def unsupported_language(code: str) -> TranslationError:
    return TranslationError(
        "TRANSLATION_UNSUPPORTED_LANGUAGE",
        "TRANSLATION_UNSUPPORTED_LANGUAGE: "
        f"'{code}' is not a supported translation language.",
    )


def invalid_input(reason: str) -> TranslationError:
    return TranslationError(
        "TRANSLATION_INVALID_INPUT",
        f"TRANSLATION_INVALID_INPUT: {reason}",
    )


def too_large(limit: int) -> TranslationError:
    return TranslationError(
        "TRANSLATION_TOO_LARGE",
        "TRANSLATION_TOO_LARGE: input exceeds the maximum of "
        f"{limit} characters.",
    )


def provider_error(detail: str) -> TranslationError:
    return TranslationError(
        "TRANSLATION_PROVIDER_ERROR",
        f"TRANSLATION_PROVIDER_ERROR: {detail}",
    )


def detection_failed() -> TranslationError:
    return TranslationError(
        "LANGUAGE_DETECTION_FAILED",
        "LANGUAGE_DETECTION_FAILED: could not confidently detect the "
        "source language; specify it explicitly.",
    )
