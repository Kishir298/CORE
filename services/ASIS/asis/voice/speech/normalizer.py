"""
A.S.I.S. voice system
Speech transcription normalization.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class NormalizationResult:
    """Result of normalizing a transcription."""

    original_text: str
    normalized_text: str
    corrections: tuple[str, ...]


class TranscriptionNormalizer:
    """
    Clean and conservatively correct speech-to-text output.

    Supports:
    - Exact phrase corrections
    - Fuzzy matching against known vocabulary
    """

    def __init__(
        self,
        custom_corrections: dict[str, str] | None = None,
        known_words: list[str] | None = None,
        fuzzy_threshold: float = 0.82,
    ) -> None:
        if not 0.0 <= fuzzy_threshold <= 1.0:
            raise ValueError("fuzzy_threshold must be between 0.0 and 1.0.")

        self.fuzzy_threshold = fuzzy_threshold

        self.corrections: dict[str, str] = {
            "rishi kurobel": "Rishik",
            "rishi korubel": "Rishik",
            "rishi kurubel": "Rishik",
            "rishita": "Rishik",
        }

        self.known_words: list[str] = [
            "Rishik",
        ]

        if custom_corrections:
            self.corrections.update(
                {key.lower(): value for key, value in custom_corrections.items()}
            )

        if known_words:
            self.known_words.extend(known_words)

        self.known_words = list(dict.fromkeys(self.known_words))

    def normalize(self, text: str) -> NormalizationResult:
        """Normalize a transcription."""

        original = text.strip()

        if not original:
            return NormalizationResult(
                original_text="",
                normalized_text="",
                corrections=(),
            )

        normalized = self._clean_text(original)
        corrections: list[str] = []

        normalized, exact_corrections = self._apply_exact_corrections(normalized)

        corrections.extend(exact_corrections)

        normalized, fuzzy_corrections = self._apply_fuzzy_corrections(normalized)

        corrections.extend(fuzzy_corrections)

        normalized = self._clean_text(normalized)

        return NormalizationResult(
            original_text=original,
            normalized_text=normalized,
            corrections=tuple(corrections),
        )

    def _apply_exact_corrections(
        self,
        text: str,
    ) -> tuple[str, list[str]]:
        """Apply exact known corrections."""

        corrections: list[str] = []

        for source, replacement in self.corrections.items():
            pattern = re.compile(
                rf"\b{re.escape(source)}\b",
                re.IGNORECASE,
            )

            if pattern.search(text):
                text = pattern.sub(
                    replacement,
                    text,
                )

                corrections.append(f"{source} -> {replacement}")

        return text, corrections

    def _apply_fuzzy_corrections(
        self,
        text: str,
    ) -> tuple[str, list[str]]:
        """
        Apply conservative fuzzy corrections.

        Only individual words are compared against the known
        vocabulary. Common short words are ignored.
        """

        corrections: list[str] = []

        words = text.split()

        for index, word in enumerate(words):
            cleaned = word.strip(".,!?;:\"'()[]{}")

            if len(cleaned) < 4:
                continue

            replacement = self._find_best_match(cleaned)

            if replacement is None:
                continue

            if cleaned.lower() == replacement.lower():
                continue

            punctuation_before = word[: len(word) - len(word.lstrip(".,!?;:\"'()[]{}"))]

            punctuation_after = word[len(word.rstrip(".,!?;:\"'()[]{}")) :]

            words[index] = f"{punctuation_before}{replacement}{punctuation_after}"

            corrections.append(f"{cleaned} -> {replacement}")

        return " ".join(words), corrections

    def _find_best_match(
        self,
        word: str,
    ) -> str | None:
        """Find the closest known vocabulary item."""

        best_match: str | None = None
        best_score = 0.0

        for known_word in self.known_words:
            score = SequenceMatcher(
                None,
                word.lower(),
                known_word.lower(),
            ).ratio()

            if score > best_score:
                best_score = score
                best_match = known_word

        if best_score >= self.fuzzy_threshold:
            return best_match

        return None

    @staticmethod
    def _clean_text(text: str) -> str:
        """Perform conservative text cleanup."""

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        text = re.sub(
            r"\s+([,.!?])",
            r"\1",
            text,
        )

        return text.strip()
