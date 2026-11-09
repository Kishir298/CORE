"""Relationship timeline + contradictions (§15-16)."""

from __future__ import annotations

from datetime import datetime


def _ts(ts: str):
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def build_timeline(messages: list[dict]) -> list[dict]:
    if not messages:
        return []
    dates = [_ts(m.get("timestamp", "")) for m in messages]
    dates = [d for d in dates if d]
    if not dates:
        return [{"label": "other", "date_range": ["", ""],
                 "confidence": "LOW", "evidence": "no timestamps"}]
    start, end = min(dates), max(dates)
    span_days = (end - start).days
    label = "close friend" if len(messages) > 1000 else "casual friend" if len(messages) > 100 else "new acquaintance"
    return [{"label": label,
             "date_range": [start.isoformat(), end.isoformat()],
             "span_days": span_days,
             "confidence": "MEDIUM",
             "evidence": f"{len(messages)} messages over {span_days}d",
             "note": "Inference from communication data, not ground truth."}]


def detect_contradictions(facts: list[dict]) -> list[dict]:
    # V1: flag same-key different values as apparent contradictions (never lies).
    by_key: dict[str, list] = {}
    for f in facts:
        by_key.setdefault(f.get("key", ""), []).append(f)
    out = []
    for k, vs in by_key.items():
        vals = {str(v.get("value")) for v in vs}
        if len(vals) > 1:
            out.append({"key": k, "statements": vs,
                        "possible_explanations": ["changed mind", "different context",
                                                  "joke/sarcasm", "misremembered"],
                        "confidence": "LOW"})
    return out
