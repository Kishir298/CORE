"""Identity matching + incremental update (§22-24). Never merge on name alone."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model import IdentityRecord


@dataclass
class MatchResult:
    identity_id: str | None
    confidence: str  # HIGH|MEDIUM|LOW|NONE
    needs_confirmation: bool
    reasons: list[str]


def _norm(name: str) -> str:
    return (name or "").strip().lower()


def match_identity(raw_name: str, identities: list[IdentityRecord],
                   context: dict[str, Any] | None = None) -> MatchResult:
    """Score alias overlap + relationship + participants. Name-only -> max MEDIUM."""
    ctx = context or {}
    name = _norm(raw_name)
    if not name:
        return MatchResult(None, "NONE", True, ["empty name"])
    best: IdentityRecord | None = None
    best_score = 0
    best_reasons: list[str] = []
    participants = {_norm(p) for p in ctx.get("participants", [])}
    for ident in identities:
        score = 0
        reasons: list[str] = []
        if name in ident.all_names():
            score += 2
            reasons.append("alias match")
        # substring both ways (Alexander vs Alex) — weak signal only
        for known in ident.all_names():
            if known and known != name and (known in name or name in known):
                score += 1
                reasons.append(f"partial alias {known}")
                break
        if ctx.get("relationship") and _norm(ctx["relationship"]) == _norm(ident.relationship):
            score += 1
            reasons.append("relationship match")
        if participants and ident.all_names() & participants:
            score += 1
            reasons.append("participant overlap")
        if score > best_score:
            best_score, best, best_reasons = score, ident, reasons
    if best is None or best_score < 2:
        return MatchResult(None, "NONE", True, ["no sufficient evidence"])
    if best_score == 2:  # name-only level
        return MatchResult(best.identity_id, "MEDIUM", True, best_reasons)
    return MatchResult(best.identity_id, "HIGH", False, best_reasons)


def apply_incremental_update(ident: IdentityRecord, new_evidence: dict[str, Any],
                             source: str) -> dict[str, Any]:
    """Merge new evidence without rebuild. Returns change summary."""
    changes: list[str] = []
    for alias in new_evidence.get("aliases", []):
        if alias and _norm(alias) not in ident.all_names():
            ident.aliases.append(alias)
            changes.append(f"alias+={alias}")
    for topic, level in new_evidence.get("interests", {}).items():
        if topic not in ident.interests:
            ident.interests[topic] = level
            changes.append(f"interest+={topic}")
    for w, c in new_evidence.get("vocabulary", {}).items():
        ident.vocabulary[w] = ident.vocabulary.get(w, 0) + int(c)
    for p, c in new_evidence.get("phrases", {}).items():
        ident.phrases[p] = ident.phrases.get(p, 0) + int(c)
    if source and source not in ident.source_conversations:
        ident.source_conversations.append(source)
    ident.touch()
    return {"identity_id": ident.identity_id, "changes": changes}
