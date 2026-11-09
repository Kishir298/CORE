"""Persona construction + router + simulator + consistency + versioning (§17,28-29,42,47-50)."""

from __future__ import annotations

from typing import Any

from .model import IdentityRecord


def build_persona(ident: IdentityRecord, era: str = "most-recent",
                  relationship: str | None = None) -> dict[str, Any]:
    rel = relationship or ident.relationship
    rel_profile = ident.relationship_profiles.get(rel, {})
    return {
        "identity_id": ident.identity_id,
        "display": ident.display_name,
        "era": era,
        "relationship": rel,
        "global": dict(ident.global_profile),
        "relationship_profile": dict(rel_profile),
        "modes": list(ident.modes.keys()),
        "vocab_sample": sorted(ident.vocabulary, key=ident.vocabulary.get, reverse=True)[:40],
        "phrases": sorted(ident.phrases, key=ident.phrases.get, reverse=True)[:20],
        "interests": dict(ident.interests),
        "unknowns": [q.get("question") for q in ident.open_questions],
        "calibration_notes": [c.get("correction") for c in ident.calibration if c.get("correction")],
        "version": len(ident.persona_versions) + 1,
    }


def route_mode(persona: dict, incoming_text: str) -> str:
    low = incoming_text.lower()
    if any(k in low for k in ("lol", "haha", "😂", "joke", "tease")) and "playful" in persona.get("modes", []):
        return "playful"
    if "?" in incoming_text and "supportive" in persona.get("modes", []):
        return "supportive"
    modes = persona.get("modes", ["direct"])
    return modes[0] if modes else "direct"


def persona_mode(persona: dict, incoming_text: str) -> str:
    """Current-tone alias for ``route_mode`` (keeps semantic name stable)."""
    return route_mode(persona, incoming_text)


def render_system_prompt(persona: dict, mode: str) -> str:
    return (
        f"You are simulating {persona.get('display')} (AI reconstruction, mode={mode}, "
        f"era={persona.get('era')}). Match vocab {persona.get('vocab_sample', [])[:12]}, "
        f"phrases {persona.get('phrases', [])[:6]}. Stay in observed style. "
        f"Never invent unsupported facts. Unknowns: {persona.get('unknowns', [])[:5]}."
    )


def render_persona_prompt(persona: dict, mode: str) -> str:
    """Canonical persona system prompt for the live simulation console.

    Same content as ``render_system_prompt``; keeps naming consistent with
    the multi-person system prompt contract in the CLI reference.
    """
    return render_system_prompt(persona, mode)


def consistency_check(generated: str, persona: dict, mode: str) -> dict[str, Any]:
    issues = []
    if len(generated) > 2000:
        issues.append("WRONG_LENGTH")
    return {"ok": not issues, "issues": issues, "mode": mode}


def save_persona_version(ident: IdentityRecord, persona: dict, reason: str) -> int:
    ident.persona_versions.append({"version": len(ident.persona_versions) + 1,
                                   "persona": persona, "reason": reason})
    ident.touch()
    return len(ident.persona_versions)
