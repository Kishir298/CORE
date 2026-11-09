"""
Speaker registration: samples -> embeddings -> stored profile.

Raw audio is never persisted; only embeddings + metadata are stored.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..models import AudioData
from ..providers import SpeakerEmbeddingProvider
from .profile import SpeakerProfile
from .store import SpeakerStore


def register_speaker(
    store: SpeakerStore,
    embedding_provider: SpeakerEmbeddingProvider,
    speaker_id: str,
    samples: Sequence[AudioData],
    name: str = "",
    metadata: dict[str, Any] | None = None,
) -> SpeakerProfile:
    """Embed ``samples`` and store them under ``speaker_id``."""
    if not speaker_id.strip():
        raise ValueError("speaker_id must be non-empty.")
    if not samples:
        raise ValueError("at least one voice sample is required.")

    embeddings = [embedding_provider.embed(audio) for audio in samples]
    existing = store.get(speaker_id)
    merged = list(existing.embeddings) if existing is not None else []
    merged.extend(embeddings)

    profile = SpeakerProfile(
        speaker_id=speaker_id,
        name=name or (existing.name if existing else ""),
        embeddings=merged,
        metadata=dict(metadata)
        if metadata is not None
        else (dict(existing.metadata) if existing else {}),
    )
    if existing is not None:
        profile.created_at = existing.created_at
    return store.register(profile)
