"""Mode discovery + triggers + transitions (§12-14). No imposed clinical labels."""

from __future__ import annotations

from collections import Counter

CANDIDATE_MODES = ("playful", "guarded", "vulnerable", "direct", "caretaking",
                   "formal", "withdrawn", "enthusiastic", "analytical",
                   "deflecting", "sarcastic", "supportive")


def discover_modes(baseline: dict, style: dict,
                   analyses: list[dict]) -> dict[str, dict]:
    purp = Counter(p for a in analyses for p in a.get("purposes", []))
    modes: dict[str, dict] = {}
    if purp.get("humor", 0) + purp.get("teasing", 0) >= 2:
        modes["playful"] = {"frequency": purp["humor"], "confidence": "MEDIUM",
                            "linguistic_signature": {"emoji_heavy": baseline.get("emoji_rate", 0) > 0.3}}
    if style.get("question_ratio", 0) > 0.3 or purp.get("requesting support", 0):
        modes["supportive"] = {"frequency": 1, "confidence": "LOW", "linguistic_signature": {}}
    if style.get("exclaim_ratio", 0) > 0.2:
        modes["enthusiastic"] = {"frequency": 1, "confidence": "LOW", "linguistic_signature": {}}
    if not modes:
        modes["direct"] = {"frequency": 1, "confidence": "LOW", "linguistic_signature": {}}
    return modes


def extract_triggers(messages: list[dict], sender: str,
                     analyses: list[dict]) -> dict[str, dict]:
    return {m.get("exchange_id", f"ex{i}"): {"preceded_by": "user message",
            "topic": "general"} for i, m in enumerate(analyses)}


def extract_transitions(analyses: list[dict]) -> list[dict]:
    seq = [a.get("mode_hint", "direct") for a in analyses]
    out = []
    for i in range(1, len(seq)):
        if seq[i] != seq[i - 1]:
            out.append({"from": seq[i-1], "to": seq[i], "type": "topic-triggered"})
    return out
