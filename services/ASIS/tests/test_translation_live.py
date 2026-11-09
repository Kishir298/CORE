"""Opt-in live validation for the MADLAD-400 translation backend.

Skipped by default. Requires installed libraries AND local weights:

    ASIS_TRANSLATION_LIVE=1 \
    ASIS_TRANSLATION_MODEL_PATH=/path/to/madlad400-3b-mt \
    python3 -m pytest tests/test_translation_live.py -v

Uses only local inference (no network); never faked.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from asis.translation.provider import MADLAD_REQUIRED_FILES

_LIVE_REQUESTED = os.getenv("ASIS_TRANSLATION_LIVE") == "1"


def _model_path() -> Path:
    return Path(os.getenv("ASIS_TRANSLATION_MODEL_PATH", "")).expanduser()


def _weights_present() -> bool:
    root = _model_path()
    if not _model_path().as_posix():
        return False
    try:
        if not root.is_dir():
            return False
    except OSError:
        return False
    missing = [n for n in MADLAD_REQUIRED_FILES if not (root / n).is_file()]
    weights = list(root.glob("*.safetensors")) + list(root.glob("*.bin"))
    return not missing and bool(weights)


pytestmark = [
    pytest.mark.skipif(
        not _LIVE_REQUESTED,
        reason="live translation tests require ASIS_TRANSLATION_LIVE=1",
    ),
    pytest.mark.skipif(
        _LIVE_REQUESTED and not _weights_present(),
        reason=(
            "MADLAD weights not installed at ASIS_TRANSLATION_MODEL_PATH; "
            "install MADLAD-400 3B MT or run with the mock provider"
        ),
    ),
]


def test_live_madlad_initializes_offline():
    from asis.translation.provider import MadladProvider

    provider = MadladProvider(model_path=str(_model_path()), device="cpu")
    assert provider.name == "madlad"
    assert provider.model_id == "google/madlad400-3b-mt"


def test_live_madlad_translates_english_french():
    from asis.translation import TranslationEngine
    from asis.translation.provider import MadladProvider

    engine = TranslationEngine(
        provider=MadladProvider(model_path=str(_model_path()), device="cpu")
    )
    result = engine.translate_text("Hello", "fr", "en")
    assert result.translated_text
    assert result.translated_text.strip().lower() != "hello"
    assert result.source_language == "en"
    assert result.target_language == "fr"
