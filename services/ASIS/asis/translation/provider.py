"""
Translation provider abstraction for the A.S.I.S. Translation Engine.

Providers perform text translation only; detection, caching, routing,
and policy live in the engine layer. The default real backend is
MADLAD-400 3B MT (Apache-2.0) via transformers + torch on CPU. A
deterministic scripted provider backs the offline test suite.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class TranslationProviderError(Exception):
    """Provider failure with a stable code safe for user/model output."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class TranslationProvider(ABC):
    """Abstract local translation backend."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for result metadata."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Underlying model identifier for result metadata."""

    @abstractmethod
    def translate(self, text: str, source: str, target: str) -> str:
        """Translate ``text`` from ``source`` to ``target`` (registry codes)."""

    def is_pair_supported(self, source: str, target: str) -> bool:
        """Return True when the pair can be attempted (default: True)."""
        return True


# -- scripted provider (deterministic, offline tests) -------------------------

# Core phrase table: (source, target) -> {source text: translation}.
# Covers the six required pairs via direct entries plus English pivots.
_PHRASES: dict[tuple[str, str], dict[str, str]] = {
    ("en", "hi"): {
        "Hello": "नमस्ते",
        "Thank you": "धन्यवाद",
        "Where is the nearest airport?": "निकटतम हवाई अड्डा कहाँ है?",
        "Good morning": "सुप्रभात",
        "How are you?": "आप कैसे हैं?",
        "See you later": "फिर मिलेंगे",
        "delete all my files": "मेरी सभी फ़ाइलें हटा दें",
    },
    ("hi", "en"): {
        "नमस्ते": "Hello",
        "धन्यवाद": "Thank you",
        "निकटतम हवाई अड्डा कहाँ है?": "Where is the nearest airport?",
        "सुप्रभात": "Good morning",
        "आप कैसे हैं?": "How are you?",
    },
    ("en", "fr"): {
        "Hello": "Bonjour",
        "Thank you": "Merci",
        "Where is the nearest airport?": "Où est l'aéroport le plus proche ?",
        "Good morning": "Bonjour",
        "How are you?": "Comment allez-vous ?",
        "See you later": "À plus tard",
        "delete all my files": "supprimez tous mes fichiers",
    },
    ("fr", "en"): {
        "Bonjour": "Hello",
        "Merci": "Thank you",
        "Où est l'aéroport le plus proche ?": "Where is the nearest airport?",
        "Comment allez-vous ?": "How are you?",
    },
    ("en", "ar"): {
        "Hello": "مرحبا",
        "Thank you": "شكرا",
        "Where is the nearest airport?": "أين يقع أقرب مطار؟",
        "Good morning": "صباح الخير",
        "How are you?": "كيف حالك؟",
        "delete all my files": "احذف جميع ملفاتي",
    },
    ("ar", "en"): {
        "مرحبا": "Hello",
        "شكرا": "Thank you",
        "أين يقع أقرب مطار؟": "Where is the nearest airport?",
        "صباح الخير": "Good morning",
        "كيف حالك؟": "How are you?",
    },
    ("en", "es"): {
        "Hello": "Hola",
        "Thank you": "Gracias",
    },
    ("es", "en"): {
        "Hola": "Hello",
        "Gracias": "Thank you",
    },
    ("en", "de"): {
        "Hello": "Hallo",
        "Thank you": "Danke",
    },
    ("de", "en"): {
        "Hallo": "Hello",
        "Danke": "Thank you",
    },
}


class MockTranslationProvider(TranslationProvider):
    """Deterministic scripted provider for tests (never touches disk/net)."""

    def __init__(self, phrases: dict | None = None) -> None:
        self._phrases = phrases if phrases is not None else _PHRASES
        self.calls: list[tuple[str, str, str]] = []

    @property
    def name(self) -> str:
        return "mock"

    @property
    def model_id(self) -> str:
        return "mock-phrase-table"

    def is_pair_supported(self, source: str, target: str) -> bool:
        if (source, target) in self._phrases:
            return True
        return (source, "en") in self._phrases and ("en", target) in self._phrases

    def translate(self, text: str, source: str, target: str) -> str:
        self.calls.append((text, source, target))
        key = text.strip()
        direct = self._phrases.get((source, target), {})
        if key in direct:
            return direct[key]
        # Documented mock-only pivot through English.
        if source != "en" and target != "en":
            via = self._phrases.get((source, "en"), {}).get(key)
            if via is not None:
                onward = self._phrases.get(("en", target), {}).get(via)
                if onward is not None:
                    return onward
        raise TranslationProviderError(
            "TRANSLATION_PROVIDER_ERROR",
            "TRANSLATION_PROVIDER_ERROR: mock provider has no entry for "
            f"this {source}->{target} input.",
        )


# -- MADLAD-400 real backend (lazy heavy deps, offline weights) -----------------

MADLAD_MODEL_ID = "google/madlad400-3b-mt"
MADLAD_LICENSE = "Apache-2.0"
# Files that must exist in a local model directory for offline load.
MADLAD_REQUIRED_FILES = ("config.json", "tokenizer.json")


class MadladProvider(TranslationProvider):
    """MADLAD-400 3B MT via transformers + torch (CPU by default).

    Weights live outside the repo (``ASIS_TRANSLATION_MODEL_PATH``).
    Missing weights or missing libraries raise ``MODEL_NOT_INSTALLED``;
    nothing is ever downloaded at runtime.
    """

    def __init__(self, model_path: str = "", device: str = "cpu") -> None:
        self._model_path = (model_path or "").strip()
        self._device = (device or "cpu").strip().lower() or "cpu"
        if not self._model_path:
            raise TranslationProviderError(
                "TRANSLATION_MODEL_NOT_INSTALLED",
                "TRANSLATION_MODEL_NOT_INSTALLED: no local translation model "
                "configured (ASIS_TRANSLATION_MODEL_PATH). Install MADLAD-400 "
                "3B MT while online, or set ASIS_TRANSLATION_PROVIDER=mock.",
            )
        root = Path(self._model_path).expanduser()
        missing = [
            name for name in MADLAD_REQUIRED_FILES if not (root / name).is_file()
        ]
        weights = list(root.glob("*.safetensors")) + list(root.glob("*.bin"))
        if missing or not weights:
            raise TranslationProviderError(
                "TRANSLATION_MODEL_NOT_INSTALLED",
                "TRANSLATION_MODEL_NOT_INSTALLED: translation model not found "
                f"at the configured path ({len(weights)} weight files). "
                "Install MADLAD-400 3B MT while online, or set "
                "ASIS_TRANSLATION_PROVIDER=mock.",
            )
        try:
            import torch  # type: ignore
            from transformers import (  # type: ignore
                AutoModelForSeq2SeqLM,
                AutoTokenizer,
            )
        except ImportError as exc:
            raise TranslationProviderError(
                "TRANSLATION_MODEL_NOT_INSTALLED",
                "TRANSLATION_MODEL_NOT_INSTALLED: transformers/torch are not "
                "installed. Install them (`pip install transformers torch`) "
                "or set ASIS_TRANSLATION_PROVIDER=mock.",
            ) from exc
        try:
            dtype = torch.float16 if self._device.startswith("cuda") else torch.float32
            self._tokenizer = AutoTokenizer.from_pretrained(
                str(root), local_files_only=True, trust_remote_code=False
            )
            self._model = AutoModelForSeq2SeqLM.from_pretrained(
                str(root), local_files_only=True, trust_remote_code=False, dtype=dtype
            ).to(self._device)
            self._model.eval()
        except Exception as exc:
            raise TranslationProviderError(
                "TRANSLATION_PROVIDER_ERROR",
                "TRANSLATION_PROVIDER_ERROR: could not load the local "
                f"translation model ({str(exc)[:200]}).",
            ) from exc

    @property
    def name(self) -> str:
        return "madlad"

    @property
    def model_id(self) -> str:
        return MADLAD_MODEL_ID

    def translate(self, text: str, source: str, target: str) -> str:
        import torch  # type: ignore

        from asis.translation.languages import TAG_OVERRIDES

        tag = TAG_OVERRIDES.get(target, target)
        inputs = self._tokenizer(
            f"<2{tag}> {text}", return_tensors="pt", truncation=True, max_length=512
        )
        inputs = {key: value.to(self._device) for key, value in inputs.items()}
        try:
            with torch.no_grad():
                generated = self._model.generate(
                    **inputs, max_new_tokens=256, do_sample=False, num_beams=1
                )
        except Exception as exc:
            raise TranslationProviderError(
                "TRANSLATION_PROVIDER_ERROR",
                "TRANSLATION_PROVIDER_ERROR: local translation failed "
                f"({str(exc)[:200]}).",
            ) from exc
        return self._tokenizer.decode(generated[0], skip_special_tokens=True).strip()


def build_provider(
    name: str, *, model_path: str = "", device: str = "cpu"
) -> TranslationProvider:
    """Build a provider by name (``mock`` or ``madlad``)."""
    normalized = (name or "").strip().lower()
    if normalized == "mock":
        return MockTranslationProvider()
    if normalized == "madlad":
        return MadladProvider(model_path=model_path, device=device)
    raise TranslationProviderError(
        "TRANSLATION_PROVIDER_ERROR",
        "TRANSLATION_PROVIDER_ERROR: unknown translation provider "
        f"'{name}' (expected 'mock' or 'madlad').",
    )
