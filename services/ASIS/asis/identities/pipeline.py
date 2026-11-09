"""End-to-end identity pipeline (§1, §56-58). import->persist->simulate->calibrate."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import analysis as A
from . import baseline as B
from . import exchanges as E
from . import modes as M
from . import timeline as T
from .matching import apply_incremental_update, match_identity
from .model import IdentityRecord, ModeDef
from .persona import build_persona, save_persona_version
from .store import IdentityStore
from .whatsapp import ConversationStore, import_export_file


def calibrate_conversation(
    db_path: Path,
    conversation_id: str,
    store: IdentityStore,
    generate,
    target: str | None = None,
    calib_ratio: float = 0.7,
) -> dict[str, Any]:
    """Self-calibration (§30-40): predict held-out replies, classify, update.

    ``generate(context_text, exchange_id) -> (predicted_text, mode)`` is the
    ONLY LLM hook; it never sees the target's actual reply. Deterministic
    scoring compares lexical/emoji/length against the real message; repeated
    same-class failures (>= 3) bump the persona version.
    """
    from . import calibration as C
    from . import exchanges as E
    from .matching import match_identity
    from .persona import build_persona, save_persona_version
    from .whatsapp import ConversationStore

    cstore = ConversationStore(db_path)
    messages = cstore.load_messages(conversation_id)
    exchanges = E.build_exchanges(messages)
    participants = target and [target] or sorted(
        {m.get("sender_raw") for m in messages
         if not (m.get("sender_raw") or "").startswith("__")}
    )
    existing = store.list_all()
    ctx = {"participants": participants}
    results: dict[str, Any] = {}
    for sender in participants:
        match = match_identity(sender, existing, ctx)
        ident = store.get(match.identity_id) if match.identity_id else None
        if ident is None:
            continue
        by_sender = [e for e in exchanges
                     if any(m.get("sender_raw") == sender for m in e.get("messages", []))]
        calib, holdout = C.chronological_split(by_sender, calib_ratio)
        if not calib:
            continue
        report = C.calibrate(calib, sender, generate)
        fail_counts: dict[str, int] = {}
        for mm in report.get("mismatches", []):
            kind = mm.get("mismatch", "UNKNOWN")
            fail_counts[kind] = fail_counts.get(kind, 0) + 1
            ident.calibration.append({
                "exchange": mm.get("exchange"),
                "mismatch": kind,
                "score": mm.get("score"),
                "correction": f"predicted outside {sender}'s observed style ({kind})",
            })
        # Holdout summary (never used for training updates by itself).
        holdout_report = C.calibrate(holdout, sender, generate) if holdout else {
            "tested": 0, "avg_composite": 0.0, "mismatches": []}
        if C.should_update(fail_counts, threshold=3):
            save_persona_version(ident, build_persona(ident), reason=f"calibrate {conversation_id}")
        store.save(ident, reason=f"calibrate {conversation_id}")
        results[sender] = {
            "identity_id": ident.identity_id,
            "tested": report["tested"],
            "avg_composite": report["avg_composite"],
            "holdout_avg": holdout_report.get("avg_composite", 0.0),
            "mismatches": report.get("mismatches", []),
            "updated": C.should_update(fail_counts, threshold=3),
        }
    return {"conversation_id": conversation_id,
            "participants": list(results), "results": results,
            "status": "ok" if results else "no-identities"}


def analyze_conversation(db_path: Path, export_path: str | Path,
                         store: IdentityStore,
                         conversation_id: str | None = None,
                         generate: Callable | None = None) -> dict[str, Any]:
    summary = import_export_file(db_path, export_path, conversation_id)
    cid = summary["conversation_id"]
    cstore = ConversationStore(db_path)
    messages = cstore.load_messages(cid)
    cstore.save_progress(cid, "exchanges", "", "", "started")
    exchanges = E.build_exchanges(messages)
    existing = store.list_all()
    # participant -> identity (match or create)
    mapping: dict[str, str] = {}
    for p in summary["participants"]:
        m = match_identity(p, existing, {"participants": summary["participants"]})
        if m.identity_id and not m.needs_confirmation:
            mapping[p] = m.identity_id
        else:
            ident = IdentityRecord(display_name=p, aliases=[p])
            store.save(ident, reason=f"import {cid}")
            existing.append(ident)
            mapping[p] = ident.identity_id
    # per-identity analysis (global + relationship-agnostic V1)
    for raw, iid in mapping.items():
        ident = store.get(iid)
        assert ident is not None
        base = B.compute_baseline(messages, raw)
        style = A.style_profile(messages, raw)
        interests = A.discover_interests(messages, raw)
        micro = [A.analyze_exchange(ex) for ex in exchanges]
        modes = M.discover_modes(base, style, micro)
        for name, md in modes.items():
            ident.modes[name] = ModeDef(mode_id=name, name=name,
                                        frequency=float(md.get("frequency", 1)),
                                        confidence=str(md.get("confidence", "LOW")))
        ident.mode_transitions = M.extract_transitions(micro)
        ident.timeline = T.build_timeline(messages)
        ident.global_profile = {"baseline": base, "style": style}
        apply_incremental_update(ident, {"aliases": [raw], "interests": interests,
                                         "vocabulary": dict(base.get("top_vocab", []))},
                                 source=cid)
        persona = build_persona(ident)
        save_persona_version(ident, persona, reason=f"analyze {cid}")
        store.save(ident, reason=f"analyze {cid}")
    if generate is not None:
        calibrate_conversation(db_path, cid, store, generate, calib_ratio=0.7)
    cstore.save_progress(cid, "done", "", "", "done")
    first = store.get(next(iter(mapping.values()))) if mapping else None
    gaps = len(first.open_questions) if first else 0
    return {"conversation_id": cid, "messages": summary["messages"],
            "participants": summary["participants"], "mapping": mapping,
            "open_gaps": gaps, "status": "ok"}
