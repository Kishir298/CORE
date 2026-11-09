"""Phase 1 micro + Phase 2 style + interests (§9-11). LLM only for semantics."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

PURPOSES = ("asserting", "asking", "directing", "promising", "expressing emotion",
            "phatic", "requesting support", "seeking information", "humor",
            "teasing", "repairing", "closing", "opening")

_Q_RE = re.compile(r"\?\s*$")
_SORRY_RE = re.compile(r"\bsorr(y|ies)\b", re.I)
_THANKS_RE = re.compile(r"\b(thanks|thank you|thx|ty)\b", re.I)


def analyze_exchange(exchange: dict[str, Any]) -> dict[str, Any]:
    """Deterministic micro-analysis. LLM paraphrase hook fills `paraphrase_llm`."""
    msgs = exchange.get("messages", [])
    texts = [m.get("text", "") for m in msgs]
    joined = "\n".join(texts)
    purposes: list[str] = []
    if any("?" in t for t in texts):
        purposes.append("asking")
    if _THANKS_RE.search(joined):
        purposes.append("expressing emotion")
    if _SORRY_RE.search(joined):
        purposes.append("repairing")
    if any(t.strip().lower() in ("lol", "haha", "lmao", "😂", "🤣") or "😂" in t for t in texts):
        purposes.append("humor")
    if not purposes:
        purposes.append("asserting")
    return {
        "exchange_id": exchange.get("id"),
        "purposes": purposes,
        "directness": "direct" if any(t.strip().endswith(("!", ".")) for t in texts) else "hedged",
        "repair": bool(_SORRY_RE.search(joined)),
        "topic_shift": len(msgs) > 2,
        "confidence": "MEDIUM",
        "paraphrase": texts[0][:200] if texts else "",
        "mode_hint": "playful" if "humor" in purposes else "direct",
    }


def style_profile(messages: list[dict[str, Any]], sender: str) -> dict[str, Any]:
    mine = [m.get("text", "") for m in messages if m.get("sender_raw") == sender]
    slang = Counter()
    for t in mine:
        for w in re.findall(r"[A-Za-z']+", t.lower()):
            if w in ("lol", "lmao", "bro", "bruh", "ya", "yeah", "nah", "gonna", "wanna", "tbh", "ngl", "omg"):
                slang[w] += 1
    return {
        "sender": sender,
        "slang": dict(slang),
        "caps_ratio": sum(1 for t in mine if t.isupper() and len(t) > 3) / max(1, len(mine)),
        "question_ratio": sum(1 for t in mine if "?" in t) / max(1, len(mine)),
        "exclaim_ratio": sum(1 for t in mine if "!" in t) / max(1, len(mine)),
        "ellipsis_ratio": sum(1 for t in mine if "..." in t) / max(1, len(mine)),
        "apology_rate": sum(1 for t in mine if _SORRY_RE.search(t)) / max(1, len(mine)),
    }


def discover_interests(messages: list[dict], sender: str) -> dict[str, str]:
    """Keyword-topic buckets with ONE_OFF/REPEATED/STRONG levels."""
    topics = {"football": 0, "music": 0, "movies": 0, "work": 0,
              "family": 0, "food": 0, "travel": 0, "gaming": 0, "study": 0}
    for m in messages:
        if m.get("sender_raw") != sender:
            continue
        low = m.get("text", "").lower()
        for k in topics:
            if k in low or (k == "gaming" and "minecraft" in low) or (k == "football" and "club" in low):
                topics[k] += 1
    out: dict[str, str] = {}
    for k, c in topics.items():
        if c >= 5:
            out[k] = "STRONG_INTEREST"
        elif c >= 2:
            out[k] = "REPEATED"
        elif c == 1:
            out[k] = "ONE_OFF"
    return out
