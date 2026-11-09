"""
Speaker identification package.

Modular: profile / store / embeddings / identifier / registration.
"""

from .embeddings import (
    SpeechBrainEmbeddingProvider,
    best_match,
    cosine_similarity,
    mean_embedding,
)
from .identifier import EmbeddingSpeakerIdentifier
from .profile import SpeakerProfile
from .registration import register_speaker
from .store import SpeakerStore

__all__ = [
    "EmbeddingSpeakerIdentifier",
    "SpeakerProfile",
    "SpeakerStore",
    "SpeechBrainEmbeddingProvider",
    "best_match",
    "cosine_similarity",
    "mean_embedding",
    "register_speaker",
]
