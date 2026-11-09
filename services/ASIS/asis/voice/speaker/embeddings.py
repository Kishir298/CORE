"""
Speaker embedding providers and similarity matching.

The pipeline depends on :class:`SpeakerEmbeddingProvider`, never on a
specific model. Cosine similarity is pure-python so matching works
without numpy/torch in tests.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from asis.errors import SpeakerRecognitionError

from ..models import AudioData
from ..providers import SpeakerEmbeddingProvider


def _to_float_list(samples: object) -> list[float]:
    """Flatten AudioData samples to a plain float list (no numpy needed)."""
    if samples is None:
        return []
    try:
        import numpy as np  # type: ignore

        if isinstance(samples, np.ndarray):
            return [float(v) for v in samples.flatten().tolist()]
    except ImportError:
        pass
    if isinstance(samples, (list, tuple)):
        out: list[float] = []
        for item in samples:
            if isinstance(item, (list, tuple)):
                out.extend(float(v) for v in item)
            else:
                try:
                    out.append(float(item))  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    continue
        return out
    return []


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Return cosine similarity in [-1, 1]; 0.0 when undefined."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (na * nb)))


def mean_embedding(embeddings: Sequence[Sequence[float]]) -> list[float]:
    """Average a set of same-length embeddings."""
    if not embeddings:
        return []
    dim = len(embeddings[0])
    acc = [0.0] * dim
    for emb in embeddings:
        if len(emb) != dim:
            raise ValueError("all embeddings must share one dimension.")
        for i, v in enumerate(emb):
            acc[i] += float(v)
    n = float(len(embeddings))
    return [v / n for v in acc]


def best_match(
    query: Sequence[float],
    profiles: Sequence[tuple[str, Sequence[float]]],
    metric: str = "cosine",
) -> tuple[str | None, float]:
    """Return (speaker_id, score) of the closest profile or (None, 0.0)."""
    if metric != "cosine":
        raise ValueError(f"unsupported similarity metric: {metric}")
    best_id: str | None = None
    best_score = 0.0
    for speaker_id, reference in profiles:
        score = cosine_similarity(query, reference)
        if score > best_score:
            best_score = score
            best_id = speaker_id
    return best_id, best_score


class SpeechBrainEmbeddingProvider(SpeakerEmbeddingProvider):
    """Local ECAPA embedding provider (optional heavy dependency).

    Lazily imports ``speechbrain``/``torch`` so base installs and tests
    never require them. Configure via constructor, never via globals.
    """

    def __init__(
        self,
        model: str = "speechbrain/spkrec-ecapa-voxceleb",
        device: str = "cpu",
    ) -> None:
        self._model_name = model
        self._device = device
        self._embedder: object | None = None
        try:
            from speechbrain.inference.speaker import EncoderClassifier  # type: ignore
        except ImportError as exc:
            raise SpeakerRecognitionError(
                "speechbrain is not installed. Install voice extras "
                "(`pip install -r requirements/voice.txt`) or set "
                "ASIS_VOICE_SPEAKER_ENGINE=mock."
            ) from exc
        try:
            self._embedder = EncoderClassifier.from_hparams(
                source=model, run_opts={"device": device}
            )
        except Exception as exc:
            from asis.voice.model_cache import model_missing_message

            raise SpeakerRecognitionError(
                model_missing_message(
                    engine="speaker",
                    model=str(model),
                    setting="ASIS_VOICE_SPEAKER_ENGINE",
                    detail=str(exc)[:200],
                )
            ) from exc

    def embed(self, audio: AudioData) -> list[float]:
        if self._embedder is None:
            raise SpeakerRecognitionError("speaker embedder is not initialized.")
        samples = _to_float_list(audio.samples)
        if not samples:
            raise SpeakerRecognitionError("no audio samples to embed.")
        try:
            import torch  # type: ignore

            waveform = torch.tensor(samples, dtype=torch.float32).unsqueeze(0)
            with torch.no_grad():
                embedding = self._embedder.encode_batch(waveform)  # type: ignore[union-attr]
                vector = embedding.squeeze().cpu().tolist()
            return [float(v) for v in vector]
        except Exception as exc:
            raise SpeakerRecognitionError(
                f"embedding extraction failed: {exc}"
            ) from exc
