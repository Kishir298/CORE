"""
Speaker profile storage for A.S.I.S. voice.

JSON-file + in-memory store. No database dependency in the voice layer.
Raw audio is never persisted here — only embeddings + metadata.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .profile import SpeakerProfile


class SpeakerStore:
    """Manage :class:`SpeakerProfile` objects with optional JSON persistence."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._profiles: dict[str, SpeakerProfile] = {}
        if self._path is not None and self._path.exists():
            self.load()

    @property
    def path(self) -> Path | None:
        return self._path

    def register(self, profile: SpeakerProfile) -> SpeakerProfile:
        """Add or replace a profile; persists when a path is configured."""
        if not isinstance(profile, SpeakerProfile):
            raise ValueError("profile must be a SpeakerProfile.")
        profile.updated_at = datetime.now(UTC).isoformat()
        self._profiles[profile.speaker_id] = profile
        if self._path is not None:
            self.save()
        return profile

    def get(self, speaker_id: str) -> SpeakerProfile | None:
        return self._profiles.get(speaker_id)

    def list_profiles(self) -> list[SpeakerProfile]:
        return list(self._profiles.values())

    def delete(self, speaker_id: str) -> bool:
        """Remove a profile; returns True when something was removed."""
        if speaker_id not in self._profiles:
            return False
        del self._profiles[speaker_id]
        if self._path is not None:
            self.save()
        return True

    def clear(self) -> None:
        self._profiles.clear()
        if self._path is not None:
            self.save()

    def save(self) -> None:
        """Write all profiles to the JSON file (when configured)."""
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {sid: p.to_dict() for sid, p in self._profiles.items()}
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load(self) -> None:
        """Load profiles from the JSON file (when configured)."""
        if self._path is None or not self._path.exists():
            return
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        self._profiles = {
            sid: SpeakerProfile.from_dict(data) for sid, data in raw.items()
        }
