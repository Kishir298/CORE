"""Identity data model + provenance + memory categories (§2-4, §17-20)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class Provenance(StrEnum):
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    EXTRAPOLATED = "EXTRAPOLATED"
    USER_CONFIRMED = "USER_CONFIRMED"
    UNKNOWN = "UNKNOWN"


class MemoryClass(StrEnum):
    CORE = "CORE"
    DYNAMIC = "DYNAMIC"
    EVIDENCE = "EVIDENCE"
    UNCERTAIN = "UNCERTAIN"
    USER_CONFIRMED = "USER_CONFIRMED"
    CALIBRATION = "CALIBRATION"


class Confidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


def new_identity_id() -> str:
    return f"identity_{uuid.uuid4().hex[:8]}"


@dataclass
class Evidence:
    source_conversation: str
    source_message_id: str
    timestamp: str
    observation_type: str
    confidence: str = "MEDIUM"
    sensitivity: str = "normal"
    text: str = ""


@dataclass
class ModeDef:
    mode_id: str
    name: str
    description: str = ""
    linguistic_signature: dict[str, Any] = field(default_factory=dict)
    message_length: dict[str, float] = field(default_factory=dict)
    punctuation: dict[str, float] = field(default_factory=dict)
    emoji_pattern: dict[str, float] = field(default_factory=dict)
    vocabulary: list[str] = field(default_factory=list)
    latency: dict[str, float] = field(default_factory=dict)
    topic_associations: list[str] = field(default_factory=list)
    relationship_associations: list[str] = field(default_factory=list)
    frequency: float = 0.0
    confidence: str = "LOW"
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class Fact:
    key: str
    value: Any
    provenance: Provenance = Provenance.OBSERVED
    memory_class: MemoryClass = MemoryClass.EVIDENCE
    confidence: str = "MEDIUM"
    evidence: list[Evidence] = field(default_factory=list)
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class IdentityRecord:
    """Persistent multi-identity record (§19). Never keyed by display name."""

    identity_id: str = field(default_factory=new_identity_id)
    display_name: str = ""
    aliases: list[str] = field(default_factory=list)
    identity_type: str = "PERSON"  # USER | PERSON | THIRD_PARTY
    relationship: str = "other"
    global_profile: dict[str, Any] = field(default_factory=dict)
    relationship_profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    interests: dict[str, str] = field(default_factory=dict)  # topic -> ONE_OFF|REPEATED|...
    modes: dict[str, ModeDef] = field(default_factory=dict)
    mode_triggers: dict[str, dict[str, Any]] = field(default_factory=dict)
    mode_transitions: list[dict[str, Any]] = field(default_factory=list)
    vocabulary: dict[str, int] = field(default_factory=dict)
    phrases: dict[str, int] = field(default_factory=dict)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    known_facts: dict[str, Fact] = field(default_factory=dict)
    uncertain_facts: dict[str, Fact] = field(default_factory=dict)
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    open_questions: list[dict[str, Any]] = field(default_factory=list)
    calibration: list[dict[str, Any]] = field(default_factory=list)
    persona_versions: list[dict[str, Any]] = field(default_factory=list)
    source_conversations: list[str] = field(default_factory=list)
    sensitivity: str = "normal"
    confidence: str = "MEDIUM"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def all_names(self) -> set[str]:
        names = {self.display_name.strip().lower()} if self.display_name else set()
        for a in self.aliases:
            if a and a.strip():
                names.add(a.strip().lower())
        return {n for n in names if n}

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity_id": self.identity_id,
            "display_name": self.display_name,
            "aliases": list(self.aliases),
            "identity_type": self.identity_type,
            "relationship": self.relationship,
            "global_profile": dict(self.global_profile),
            "relationship_profiles": {k: dict(v) for k, v in self.relationship_profiles.items()},
            "interests": dict(self.interests),
            "modes": {k: {"mode_id": m.mode_id, "name": m.name} for k, m in self.modes.items()},
            "timeline": list(self.timeline),
            "known_facts": {k: {"value": f.value, "provenance": str(f.provenance)} for k, f in self.known_facts.items()},
            "open_questions": list(self.open_questions),
            "source_conversations": list(self.source_conversations),
            "confidence": self.confidence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
