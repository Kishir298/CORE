"""Self-calibration engine (§30-40, §43-44, §59-60). Target hidden during prediction."""

from __future__ import annotations

import re
from collections.abc import Callable
from difflib import SequenceMatcher
from typing import Any

EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]")


def chronological_split(exchanges: list[dict], calib_ratio: float = 0.7) -> tuple[list, list]:
    n = int(len(exchanges) * calib_ratio)
    return exchanges[:n], exchanges[n:]


def compare_responses(generated: str, actual: str) -> dict[str, Any]:
    lex = SequenceMatcher(None, generated.lower(), actual.lower()).ratio()
    ge, ae = len(EMOJI_RE.findall(generated)), len(EMOJI_RE.findall(actual))
    emoji_sim = 1.0 - min(1.0, abs(ge - ae) / max(1, max(ge, ae)))
    llen = 1.0 - min(1.0, abs(len(generated) - len(actual)) / max(1, max(len(generated), len(actual))))
    return {"lexical": round(lex, 3), "emoji": round(emoji_sim, 3),
            "length": round(llen, 3),
            "composite": round(0.5 * lex + 0.25 * emoji_sim + 0.25 * llen, 3),
            "exact": generated.strip() == actual.strip()}


def classify_mismatch(generated: str, actual: str, gen_mode: str, act_mode: str) -> str:
    if gen_mode != act_mode:
        return "WRONG_MODE"
    c = compare_responses(generated, actual)
    if c["length"] < 0.5:
        return "WRONG_LENGTH"
    if c["emoji"] < 0.5:
        return "WRONG_EMOJI"
    if c["lexical"] < 0.4:
        return "WRONG_VOCABULARY"
    return "UNKNOWN"


def calibrate(calib_set: list[dict], target_sender: str,
              generate: Callable[[str, str], tuple[str, str]]) -> dict[str, Any]:
    """generate(context_text, exchange_id) -> (predicted, mode). Never sees target."""
    mismatches: list[dict] = []
    scores: list[float] = []
    for ex in calib_set:
        msgs = ex.get("messages", [])
        # target = last message by target_sender; context = everything before
        idx = max((i for i, m in enumerate(msgs) if m.get("sender_raw") == target_sender), default=-1)
        if idx <= 0:
            continue
        context = "\n".join(m.get("text", "") for m in msgs[:idx])
        actual = msgs[idx].get("text", "")
        predicted, mode = generate(context, ex.get("id", ""))
        comp = compare_responses(predicted, actual)
        scores.append(comp["composite"])
        if comp["composite"] < 0.75:
            mismatches.append({"exchange": ex.get("id"),
                               "mismatch": classify_mismatch(predicted, actual, mode, mode),
                               "score": comp["composite"]})
    return {"tested": len(scores),
            "avg_composite": round(sum(scores)/len(scores), 3) if scores else 0,
            "mismatches": mismatches}


def should_update(fail_counts: dict[str, int], threshold: int = 3) -> list[str]:
    """Single mismatch -> flag; repeated -> investigate; consistent -> update."""
    return [k for k, v in fail_counts.items() if v >= threshold]
