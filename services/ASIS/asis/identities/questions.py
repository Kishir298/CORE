"""Question engine (§25-26). Asks only high-impact unknowns."""

from __future__ import annotations

from typing import Any


def detect_gaps(ident) -> list[dict[str, Any]]:
    gaps = []
    for topic, level in ident.interests.items():
        if level in ("REPEATED", "STRONG_INTEREST"):
            gaps.append({"question": f"What is {ident.display_name}'s favorite {topic}?",
                         "topic": topic, "impact": 8, "uncertainty": 7})
    for q in ident.open_questions:
        gaps.append({"question": q.get("question", ""), "topic": "general",
                     "impact": 6, "uncertainty": 8})
    if not gaps:
        gaps.append({"question": f"What should I know about {ident.display_name}?",
                     "topic": "general", "impact": 5, "uncertainty": 5})
    return sorted(gaps, key=lambda g: g["impact"] * g["uncertainty"], reverse=True)[:5]


def apply_user_answer(ident, question: str, answer: str) -> dict:
    from .model import Fact, MemoryClass, Provenance
    key = question.strip().lower()[:80]
    ident.known_facts[key] = Fact(key=key, value=answer,
                                  provenance=Provenance.USER_CONFIRMED,
                                  memory_class=MemoryClass.USER_CONFIRMED,
                                  confidence="HIGH")
    ident.open_questions = [q for q in ident.open_questions if q.get("question") != question]
    ident.touch()
    return {"stored": key, "provenance": "USER_CONFIRMED"}
