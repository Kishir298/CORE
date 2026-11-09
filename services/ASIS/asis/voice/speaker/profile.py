"""
Speaker profile model for A.S.I.S. voice.

Voice identity state lives here, not in conversational memory.
Profiles store embeddings + metadata, never raw audio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class SpeakerProfile:
    """A registered speaker with embedding vectors."""

    speaker_id: str
    name: str = ""
    embeddings: list[list[float]] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow_iso)
    updated_at: str = field(default_factory=_utcnow_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.speaker_id, str) or not self.speaker_id.strip():
            raise ValueError("speaker_id must be a non-empty str.")
        if not isinstance(self.name, str):
            raise ValueError("name must be a str.")
        if not isinstance(self.embeddings, list):
            raise ValueError("embeddings must be a list.")
        for emb in self.embeddings:
            if not isinstance(emb, list) or not emb:
                raise ValueError("each embedding must be a non-empty list.")
            for v in emb:
                if not isinstance(v, (int, float)):
                    raise ValueError("embedding values must be numbers.")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dict.")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "speaker_id": self.speaker_id,
            "name": self.name,
            "embeddings": [list(e) for e in self.embeddings],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpeakerProfile:
        """Deserialize from :meth:`to_dict` output."""
        return cls(
            speaker_id=data["speaker_id"],
            name=data.get("name", ""),
            embeddings=[list(e) for e in data.get("embeddings", [])],
            created_at=data.get("created_at", _utcnow_iso()),
            updated_at=data.get("updated_at", _utcnow_iso()),
            metadata=dict(data.get("metadata", {})),
        )
