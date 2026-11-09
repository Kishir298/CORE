"""Exchange unit builder (§7). Preserves original sequence as authoritative."""

from __future__ import annotations

from datetime import datetime
from typing import Any

LONG_GAP_S = 4 * 3600


def _parse_ts(ts: str) -> float | None:
    try:
        return datetime.fromisoformat(ts).timestamp()
    except Exception:
        return None


def build_exchanges(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group bursts + replies. Each exchange: {id, messages, initiator, gap_before_s}."""
    exchanges: list[dict[str, Any]] = []
    cur: list[dict] = []
    prev_ts: float | None = None
    prev_sender: str | None = None
    for m in messages:
        ts = _parse_ts(m.get("timestamp", ""))
        gap = (ts - prev_ts) if (ts is not None and prev_ts is not None) else 0
        sender = m.get("sender_raw", "")
        # New exchange on long gap or return to initiator after alternation
        if cur and (gap > LONG_GAP_S or (len(cur) >= 2 and sender == cur[0].get("sender_raw") and prev_sender != sender and len(cur) >= 4)):
            exchanges.append({"id": f"ex_{len(exchanges):05d}",
                              "messages": cur,
                              "initiator": cur[0].get("sender_raw"),
                              "gap_before_s": 0})
            cur = []
        cur.append(m)
        prev_ts, prev_sender = ts, sender
        # Close on sender alternation pair with pause
        if len(cur) >= 2 and cur[-1].get("sender_raw") != cur[-2].get("sender_raw") and gap > 600:
            exchanges.append({"id": f"ex_{len(exchanges):05d}", "messages": cur,
                              "initiator": cur[0].get("sender_raw"), "gap_before_s": 0})
            cur = []
    if cur:
        exchanges.append({"id": f"ex_{len(exchanges):05d}", "messages": cur,
                          "initiator": cur[0].get("sender_raw"), "gap_before_s": 0})
    return exchanges
