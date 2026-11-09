"""Storage-domain routing for ASIS-owned persistence.

Local SQLite/JSON persistence stays canonical (see ``asis.memory``,
``asis.voice.speaker.store``). This module answers two questions without
moving any data:

1. Which persistence kinds are *local-only* vs *cloud-bound* (opt-in)?
2. Which RESCS namespace does a cloud-bound record belong to?

All cloud-bound ASIS data lives under the ``asis.`` namespace prefix
(``asis.memory``, ``asis.conversations``, ``asis.state``,
``asis.metadata``). Writes outside ``asis.`` are refused unless the
caller explicitly opts into a foreign namespace.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DOMAIN_PREFIX = "asis."

# Persistence that stays local by design (never cloud-routed).
LOCAL_ONLY_KINDS = frozenset(
    {
        "sqlite-memory",  # asis/memory (memory.db via platformdirs)
        "speaker-store",  # asis/voice speaker embeddings JSON
        "logs",  # rotating asis.log
        "translation-cache",  # in-process LRU
        "documents-session",  # in-process attachments
        "voice-temp",  # ephemeral TTS wav
    }
)

# Persistence kinds eligible for explicit cloud backup/sync.
CLOUD_BOUND_KINDS = frozenset(
    {
        "memory-export",  # curated memory records for sync
        "conversation-export",  # session transcripts marked for sync
        "state-snapshot",  # explicit agent-state snapshots
        "metadata",  # sync metadata / cursors
    }
)

_KIND_NAMESPACES = {
    "memory-export": "asis.memory",
    "conversation-export": "asis.conversations",
    "state-snapshot": "asis.state",
    "metadata": "asis.metadata",
}


class DomainError(ValueError):
    """Raised for invalid storage-domain requests."""


@dataclass(frozen=True)
class DomainRouter:
    """Routes persistence kinds to RESCS namespaces with prefix enforcement."""

    prefix: str = DOMAIN_PREFIX
    allow_foreign_namespaces: bool = False

    def classify(self, kind: str) -> str:
        """Return ``"local-only"`` or ``"cloud-bound"`` for a kind."""
        if kind in LOCAL_ONLY_KINDS:
            return "local-only"
        if kind in CLOUD_BOUND_KINDS:
            return "cloud-bound"
        raise DomainError(f"unknown persistence kind: {kind!r}")

    def namespace_for(self, kind: str) -> str:
        """Return the RESCS namespace for a cloud-bound kind."""
        if self.classify(kind) != "cloud-bound":
            raise DomainError(f"kind {kind!r} is local-only, not cloud-bound")
        return _KIND_NAMESPACES[kind]

    def check_namespace(self, namespace: str) -> str:
        """Enforce the domain prefix unless foreign namespaces are allowed."""
        if not (isinstance(namespace, str) and namespace):
            raise DomainError("namespace must be a non-empty string")
        if not self.allow_foreign_namespaces and not namespace.startswith(
            self.prefix
        ):
            raise DomainError(f"namespace {namespace!r} is outside {self.prefix!r}")
        return namespace


@dataclass
class SyncManifest:
    """Result of a migration run (sources are never deleted)."""

    copied: list[str] = field(default_factory=list)
    skipped_identical: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when nothing failed."""
        return not self.failed
