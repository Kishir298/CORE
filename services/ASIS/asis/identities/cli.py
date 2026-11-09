"""CLI handlers for /identity commands (§27, §47-48). LLM-bypassed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .persona import build_persona, route_mode
from .pipeline import analyze_conversation
from .questions import apply_user_answer, detect_gaps
from .store import IdentityStore


def _store(db: Path) -> IdentityStore:
    return IdentityStore(db)


def cmd_identities(db: Path) -> str:
    idents = _store(db).list_all()
    if not idents:
        return "Available identities:\n(none yet — /identity analyze <file>)"
    lines = ["Available identities:", ""]
    for i, ident in enumerate(idents, 1):
        lines.append(f"{i}. {ident.display_name} [{ident.identity_id}] ({ident.relationship})")
    return "\n".join(lines)


def cmd_identity(db: Path, name: str) -> str:
    for ident in _store(db).list_all():
        if ident.display_name.lower() == name.lower() or ident.identity_id == name:
            d = ident.to_dict()
            return (f"{d['display_name']} [{d['identity_id']}]\n"
                    f"aliases: {', '.join(d['aliases'])}\n"
                    f"modes: {', '.join(d['modes']) or '—'}\n"
                    f"interests: {d['interests']}\n"
                    f"sources: {', '.join(d['source_conversations'])}")
    return f"Unknown identity: {name}"


def cmd_analyze(db: Path, file: str) -> str:
    res = analyze_conversation(db, file, _store(db))
    gaps = detect_gaps(_store(db).get(next(iter(res["mapping"].values())))) if res["mapping"] else []
    out = [f"[ OK ] Parsed {res['messages']} messages",
           f"[ OK ] Participants: {', '.join(res['participants'])}",
           "[ OK ] Exchanges, baseline, modes, timeline, persona",
           f"Mapping: {res['mapping']}", ""]
    if gaps:
        out.append(f"Open gaps: {len(gaps)}")
        out.append(f"I don't have enough evidence for: {gaps[0]['question']} Do you know it?")
    return "\n".join(out)


def cmd_questions(db: Path, name: str) -> str:
    store = _store(db)
    target = next((i for i in store.list_all()
                   if i.display_name.lower() == name.lower() or i.identity_id == name), None)
    if target is None:
        return f"Unknown identity: {name}"
    gaps = detect_gaps(target)
    return "\n".join(f"- {g['question']}" for g in gaps)


def cmd_answer(db: Path, name: str, question: str, answer: str) -> str:
    store = _store(db)
    target = next((i for i in store.list_all()
                   if i.display_name.lower() == name.lower() or i.identity_id == name), None)
    if target is None:
        return f"Unknown identity: {name}"
    r = apply_user_answer(target, question, answer)
    store.save(target, reason="user answer")
    return f"[ OK ] User-confirmed fact stored: {r['stored']}."


def cmd_answer_open(db: Path, name: str, answer: str) -> str:
    """Answer the highest-impact open question for ``name``."""
    store = _store(db)
    target = next((i for i in store.list_all()
                   if i.display_name.lower() == name.lower() or i.identity_id == name), None)
    if target is None:
        return f"Unknown identity: {name}"
    gaps = detect_gaps(target)
    if not gaps:
        return f"No open questions for {name}."
    q = gaps[0]["question"]
    apply_user_answer(target, q, answer)
    store.save(target, reason="user answer")
    return f"[ OK ] Stored answer for \"{q}\" (provenance USER_CONFIRMED)."

def cmd_simulate_prompt(db: Path, name: str, incoming: str) -> dict[str, Any]:
    store = _store(db)
    target = next((i for i in store.list_all()
                   if i.display_name.lower() == name.lower() or i.identity_id == name), None)
    if target is None:
        return {"error": f"Unknown identity: {name}"}
    persona = build_persona(target)
    mode = route_mode(persona, incoming)
    from .persona import render_system_prompt
    return {"system": render_system_prompt(persona, mode), "mode": mode,
            "notice": "AI reconstruction, not the actual person."}


def cmd_export(db: Path, name: str) -> dict[str, Any]:
    store = _store(db)
    target = next((i for i in store.list_all()
                   if i.display_name.lower() == name.lower() or i.identity_id == name), None)
    if target is None:
        return {"error": f"Unknown identity: {name}"}
    return store.export_dataset(target.identity_id)


def cmd_forget(db: Path, name: str) -> str:
    store = _store(db)
    target = next((i for i in store.list_all()
                   if i.display_name.lower() == name.lower() or i.identity_id == name), None)
    if target is None:
        return f"Unknown identity: {name}"
    store.delete(target.identity_id)
    return f"[ OK ] Deleted {target.display_name} + derived records."


def cmd_calibrate(db: Path, name: str, conversation_id: str, generate) -> str:
    """Run self-calibration for ``name`` and persist corrections/versions."""
    from .pipeline import calibrate_conversation

    store = _store(db)
    target = next((i for i in store.list_all()
                   if i.display_name.lower() == name.lower() or i.identity_id == name), None)
    if target is None:
        return f"Unknown identity: {name}"
    res = calibrate_conversation(db, conversation_id, store, generate, target=name)
    r = res["results"].get(name)
    if r is None:
        return f"Calibration unavailable: {name} not in conversation {conversation_id}."
    lines = [f"[ OK ] Calibrated {name} ({r['tested']} predictions, "
             f"avg composite {r['avg_composite']}, holdout {r['holdout_avg']})"]
    if r["mismatches"]:
        lines.append("Mismatches:")
        lines.extend(f"  {m['exchange']}: {m['mismatch']} (score {m['score']})"
                     for m in r["mismatches"][:8])
    if r["updated"]:
        lines.append("[ OK ] Persona version updated from consistent mismatches.")
    else:
        lines.append("Style within tolerance; persona version unchanged.")
    return "\n".join(lines)
