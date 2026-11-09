"""Phase 0 quantitative baseline (§8). Deterministic Python only."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from statistics import median
from typing import Any

EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]")
WORD_RE = re.compile(r"[A-Za-z0-9']+")


def _ts(ts: str) -> float | None:
    try:
        return datetime.fromisoformat(ts).timestamp()
    except Exception:
        return None


def compute_baseline(messages: list[dict[str, Any]], sender: str) -> dict[str, Any]:
    mine = [m for m in messages if m.get("sender_raw") == sender]
    texts = [m.get("text", "") for m in mine]
    words = [len(WORD_RE.findall(t)) for t in texts]
    lens = [len(t) for t in texts]
    # latencies: time from other-sender message to my reply
    lat: list[float] = []
    last_other: float | None = None
    for m in messages:
        t = _ts(m.get("timestamp", ""))
        if m.get("sender_raw") == sender:
            if last_other is not None and t is not None:
                lat.append(max(0.0, t - last_other))
            last_other = None
        else:
            if t is not None:
                last_other = t
    vocab = Counter()
    for t in texts:
        vocab.update(w.lower() for w in WORD_RE.findall(t))
    emoji = sum(len(EMOJI_RE.findall(t)) for t in texts)
    punct = Counter(c for t in texts for c in t if c in "?!.,;:...-()\"'")
    bursts = sum(1 for i in range(1, len(messages))
                 if messages[i].get("sender_raw") == sender
                 and messages[i - 1].get("sender_raw") == sender)
    media = Counter(m.get("media_type", "text") for m in mine)
    initiations = 0
    for i, m in enumerate(messages):
        if m.get("sender_raw") == sender and (i == 0 or (messages[i-1].get("sender_raw") != sender)):
            prev_t = _ts(messages[i-1].get("timestamp", "")) if i else None
            cur_t = _ts(m.get("timestamp", ""))
            if i == 0 or (prev_t is not None and cur_t is not None and cur_t - prev_t > 4*3600):
                initiations += 1
    return {
        "sender": sender,
        "total_messages": len(mine),
        "total_words": sum(words),
        "avg_len": round(sum(lens)/len(lens), 2) if lens else 0,
        "median_len": median(lens) if lens else 0,
        "avg_words": round(sum(words)/len(words), 2) if words else 0,
        "latency_avg_s": round(sum(lat)/len(lat), 1) if lat else 0,
        "latency_dist": {"fast": sum(1 for x in lat if x < 120),
                         "moderate": sum(1 for x in lat if 120 <= x < 3600),
                         "slow": sum(1 for x in lat if x >= 3600)},
        "initiation_ratio": round(initiations/max(1, len(messages)), 4),
        "media": dict(media),
        "top_vocab": vocab.most_common(30),
        "emoji_count": emoji,
        "emoji_rate": round(emoji/max(1, len(mine)), 3),
        "punct": dict(punct),
        "bursts": bursts,
        "double_text_rate": round(bursts/max(1, len(mine)), 3),
    }
