"""
Embedding-based speaker identification.

Flow: audio -> embedding -> compare against registered profiles ->
best match -> threshold decision. No magic numbers: threshold and
metric come from configuration / constructor.
"""

from __future__ import annotations

from asis.errors import SpeakerRecognitionError
from asis.logging.logger import get_logger

from ..models import AudioData, SpeakerResult
from ..providers import SpeakerEmbeddingProvider, SpeakerIdentifier
from .embeddings import best_match, mean_embedding
from .store import SpeakerStore


class EmbeddingSpeakerIdentifier(SpeakerIdentifier):
    """Identify speakers by comparing embeddings to stored profiles."""

    def __init__(
        self,
        embedding_provider: SpeakerEmbeddingProvider,
        store: SpeakerStore,
        threshold: float = 0.6,
        metric: str = "cosine",
    ) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be between 0.0 and 1.0.")
        self._embeddings = embedding_provider
        self._store = store
        self._threshold = threshold
        self._metric = metric
        self._logger = get_logger("voice.speaker.identifier")

    @property
    def threshold(self) -> float:
        return self._threshold

    def identify(self, audio: AudioData) -> SpeakerResult:
        try:
            query = self._embeddings.embed(audio)
        except SpeakerRecognitionError:
            raise
        except Exception as exc:
            raise SpeakerRecognitionError(f"embedding failed: {exc}") from exc

        profiles = self._store.list_profiles()
        if not profiles:
            return SpeakerResult(speaker_id="unknown", confidence=0.0, is_known=False)

        references: list[tuple[str, list[float]]] = []
        for profile in profiles:
            if not profile.embeddings:
                continue
            try:
                references.append(
                    (profile.speaker_id, mean_embedding(profile.embeddings))
                )
            except ValueError:
                continue

        if not references:
            return SpeakerResult(speaker_id="unknown", confidence=0.0, is_known=False)

        try:
            best_id, score = best_match(query, references, metric=self._metric)
        except ValueError as exc:
            raise SpeakerRecognitionError(str(exc)) from exc

        confidence = max(0.0, min(1.0, float(score)))
        if best_id is not None and confidence >= self._threshold:
            self._logger.debug("speaker identified: %s (%.3f)", best_id, confidence)
            return SpeakerResult(
                speaker_id=best_id, confidence=confidence, is_known=True
            )

        return SpeakerResult(
            speaker_id="unknown", confidence=confidence, is_known=False
        )
