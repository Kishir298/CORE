"""Persistent identity store (SQLite) + RESCS export envelope (§19, §46)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .model import Fact, IdentityRecord, MemoryClass, Provenance


class IdentityStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        con = self._connect()
        try:
            con.execute(
                """CREATE TABLE IF NOT EXISTS identities (
                    identity_id TEXT PRIMARY KEY, display_name TEXT,
                    aliases TEXT, identity_type TEXT, relationship TEXT,
                    data TEXT, created_at TEXT, updated_at TEXT)"""
            )
            con.execute(
                """CREATE TABLE IF NOT EXISTS identity_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, identity_id TEXT,
                    ts TEXT, op TEXT, reason TEXT)"""
            )
            con.commit()
        finally:
            con.close()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    def save(self, ident: IdentityRecord, reason: str = "upsert") -> None:
        from datetime import UTC, datetime
        con = self._connect()
        try:
            con.execute(
                "INSERT OR REPLACE INTO identities VALUES (?,?,?,?,?,?,?,?)",
                (ident.identity_id, ident.display_name, json.dumps(ident.aliases),
                 ident.identity_type, ident.relationship,
                 json.dumps(_serialize(ident)), ident.created_at, ident.updated_at),
            )
            con.execute("INSERT INTO identity_events (identity_id, ts, op, reason) VALUES (?,?,?,?)",
                        (ident.identity_id, datetime.now(UTC).isoformat(), "save", reason))
            con.commit()
        finally:
            con.close()

    def get(self, identity_id: str) -> IdentityRecord | None:
        con = self._connect()
        try:
            row = con.execute("SELECT * FROM identities WHERE identity_id=?",
                              (identity_id,)).fetchone()
        finally:
            con.close()
        return _deserialize(json.loads(row["data"])) if row else None

    def list_all(self) -> list[IdentityRecord]:
        con = self._connect()
        try:
            rows = con.execute("SELECT data FROM identities ORDER BY display_name").fetchall()
        finally:
            con.close()
        return [_deserialize(json.loads(r["data"])) for r in rows]

    def delete(self, identity_id: str) -> bool:
        """Cascade: identity + derived events. Caller must also purge memories/calibration."""
        from datetime import UTC, datetime
        con = self._connect()
        try:
            cur = con.execute("DELETE FROM identities WHERE identity_id=?", (identity_id,))
            con.execute("INSERT INTO identity_events (identity_id, ts, op, reason) VALUES (?,?,?,?)",
                        (identity_id, datetime.now(UTC).isoformat(), "delete", "user request"))
            con.commit()
            return cur.rowcount > 0
        finally:
            con.close()

    def export_dataset(self, identity_id: str) -> dict[str, Any]:
        """Training-export envelope for optional future fine-tuning (§46)."""
        ident = self.get(identity_id)
        if ident is None:
            raise KeyError(identity_id)
        return {"identity_id": identity_id, "display": ident.display_name,
                "messages": [], "persona_version": len(ident.persona_versions),
                "note": "Core system works without fine-tuning."}


def _serialize(ident: IdentityRecord) -> dict:
    return {
        "identity_id": ident.identity_id, "display_name": ident.display_name,
        "aliases": ident.aliases, "identity_type": ident.identity_type,
        "relationship": ident.relationship, "global_profile": ident.global_profile,
        "relationship_profiles": ident.relationship_profiles,
        "interests": ident.interests,
        "modes": {k: {"mode_id": m.mode_id, "name": m.name,
                      "description": m.description, "frequency": m.frequency,
                      "confidence": m.confidence} for k, m in ident.modes.items()},
        "mode_triggers": ident.mode_triggers, "mode_transitions": ident.mode_transitions,
        "vocabulary": ident.vocabulary, "phrases": ident.phrases,
        "timeline": ident.timeline,
        "known_facts": {k: {"key": f.key, "value": f.value,
                            "provenance": str(f.provenance),
                            "memory_class": str(f.memory_class),
                            "confidence": f.confidence} for k, f in ident.known_facts.items()},
        "uncertain_facts": {k: {"key": f.key, "value": f.value} for k, f in ident.uncertain_facts.items()},
        "contradictions": ident.contradictions, "open_questions": ident.open_questions,
        "calibration": ident.calibration, "persona_versions": ident.persona_versions[-5:],
        "source_conversations": ident.source_conversations,
        "confidence": ident.confidence, "created_at": ident.created_at,
        "updated_at": ident.updated_at,
    }


def _deserialize(d: dict) -> IdentityRecord:
    from .model import ModeDef
    ident = IdentityRecord(identity_id=d.get("identity_id", ""),
                           display_name=d.get("display_name", ""),
                           aliases=d.get("aliases", []),
                           identity_type=d.get("identity_type", "PERSON"),
                           relationship=d.get("relationship", "other"))
    ident.global_profile = d.get("global_profile", {})
    ident.relationship_profiles = d.get("relationship_profiles", {})
    ident.interests = d.get("interests", {})
    for k, m in d.get("modes", {}).items():
        ident.modes[k] = ModeDef(mode_id=m.get("mode_id", k), name=m.get("name", k),
                                 description=m.get("description", ""),
                                 frequency=m.get("frequency", 0.0),
                                 confidence=m.get("confidence", "LOW"))
    ident.mode_triggers = d.get("mode_triggers", {})
    ident.mode_transitions = d.get("mode_transitions", [])
    ident.vocabulary = d.get("vocabulary", {})
    ident.phrases = d.get("phrases", {})
    ident.timeline = d.get("timeline", [])
    for k, f in d.get("known_facts", {}).items():
        ident.known_facts[k] = Fact(key=k, value=f.get("value"),
                                    provenance=Provenance(f.get("provenance", "OBSERVED")),
                                    memory_class=MemoryClass.CALIBRATION if False else MemoryClass.EVIDENCE)
    ident.contradictions = d.get("contradictions", [])
    ident.open_questions = d.get("open_questions", [])
    ident.calibration = d.get("calibration", [])
    ident.persona_versions = d.get("persona_versions", [])
    ident.source_conversations = d.get("source_conversations", [])
    ident.confidence = d.get("confidence", "MEDIUM")
    ident.created_at = d.get("created_at", ident.created_at)
    ident.updated_at = d.get("updated_at", ident.updated_at)
    return ident
