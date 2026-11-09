"""Deterministic identity subsystem tests (mock-only, no network/models)."""

from __future__ import annotations

from pathlib import Path

from asis.identities import analysis as A
from asis.identities import baseline as B
from asis.identities import calibration as C
from asis.identities import cli as ICLI
from asis.identities import exchanges as E
from asis.identities.matching import apply_incremental_update, match_identity
from asis.identities.model import IdentityRecord
from asis.identities.persona import build_persona, route_mode
from asis.identities.pipeline import analyze_conversation
from asis.identities.questions import apply_user_answer, detect_gaps
from asis.identities.store import IdentityStore
from asis.identities.whatsapp import ConversationStore, parse_whatsapp_export

SAMPLE = """[12/03/24, 10:00:00] Alex: hey bro 😂
[12/03/24, 10:01:00] Me: lol hey! how was football?
[12/03/24, 10:02:00] Alex: it was great
we won 2-0
[12/03/24, 10:05:00] Alex: <Media omitted>
[12/03/24, 10:06:00] Me: nice!
This is a bad line without header continuation
[12/03/24, 10:07:00] Alex: You deleted this message.
"""


def _write(tmp_path: Path) -> Path:
    p = tmp_path / "Chat_A.txt"
    p.write_text(SAMPLE, encoding="utf-8")
    return p


def test_parser_multiline_media_malformed(tmp_path):
    p = _write(tmp_path)
    msgs = parse_whatsapp_export(p, "Chat_A")
    assert len(msgs) >= 6  # never discards
    alex_first = [m for m in msgs if m.sender_raw == "Alex"][0]
    assert "hey bro" in alex_first.text
    multi = [m for m in msgs if "we won" in m.text]
    assert multi and multi[0].sender_raw == "Alex"
    assert any(m.media_type == "image" for m in msgs)
    assert any(m.media_type == "deleted" for m in msgs)
    # continuation line preserved
    assert any("bad line" in m.text for m in msgs)


def test_store_progress(tmp_path):
    p = _write(tmp_path)
    db = tmp_path / "wa.db"
    from asis.identities.whatsapp import import_export_file
    res = import_export_file(db, p, "Chat_A")
    assert res["messages"] >= 6 and "Alex" in res["participants"]
    store = ConversationStore(db)
    assert len(store.load_messages("Chat_A")) == res["messages"]
    assert store.load_progress("Chat_A")["status"] == "done"


def test_exchanges_baseline_modes(tmp_path):
    p = _write(tmp_path)
    msgs = parse_whatsapp_export(p, "Chat_A")
    dicts = [m.__dict__ for m in msgs]
    ex = E.build_exchanges(dicts)
    assert ex and sum(len(x["messages"]) for x in ex) == len(dicts)
    base = B.compute_baseline(dicts, "Alex")
    assert base["total_messages"] >= 3 and base["emoji_count"] >= 1
    style = A.style_profile(dicts, "Alex")
    assert "question_ratio" in style
    micro = [A.analyze_exchange(x) for x in ex]
    assert all("purposes" in m for m in micro)
    interests = A.discover_interests(dicts, "Me")
    assert interests.get("football") in (None, "ONE_OFF", "REPEATED", "STRONG_INTEREST")


def test_matching_never_name_only(tmp_path):
    ident = IdentityRecord(display_name="Alex", aliases=["Alex"])
    r = match_identity("Alexander", [ident], {})
    assert r.identity_id is None or r.needs_confirmation  # name-only insufficient
    r2 = match_identity("Alex", [ident], {"participants": ["alex", "me"]})
    assert r2.identity_id == ident.identity_id


def test_incremental_and_questions(tmp_path):
    ident = IdentityRecord(display_name="Alex", aliases=["Alex"])
    ch = apply_incremental_update(ident, {"aliases": ["Al"], "interests": {"football": "REPEATED"},
                                          "vocabulary": {"bro": 3}}, source="Chat_A")
    assert "alias+=Al" in ch["changes"] and ident.vocabulary["bro"] == 3
    gaps = detect_gaps(ident)
    assert gaps and "football" in gaps[0]["question"].lower()
    apply_user_answer(ident, gaps[0]["question"], "Manchester United")
    assert ident.known_facts


def test_pipeline_persist_restart(tmp_path):
    p = _write(tmp_path)
    db = tmp_path / "all.db"
    store = IdentityStore(db)
    res = analyze_conversation(db, p, store, "Chat_A")
    assert res["status"] == "ok" and res["mapping"]
    # restart: new store object, still available
    store2 = IdentityStore(db)
    assert len(store2.list_all()) >= 2
    # second import updates, not duplicates
    analyze_conversation(db, p, store2, "Chat_A")
    assert len(store2.list_all()) == len(store.list_all())


def test_persona_router_calibration():
    ident = IdentityRecord(display_name="Alex", aliases=["Alex"])
    ident.vocabulary = {"bro": 5, "lol": 3}
    ident.modes = {}
    persona = build_persona(ident)
    assert persona["identity_id"] == ident.identity_id
    assert route_mode({**persona, "modes": ["playful"]}, "lol that was funny") == "playful"
    comp = C.compare_responses("hey bro 😂", "hey bro 😂")
    assert comp["exact"] and comp["composite"] == 1.0
    cal, val = C.chronological_split([{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}])
    assert len(cal) == 2 and len(val) == 2
    # target hidden: generate never receives actual
    seen = {}
    def gen(ctx, eid):
        seen[eid] = ctx
        return "hi bro", "playful"
    out = C.calibrate([{"id": "e1", "messages": [
        {"sender_raw": "Me", "text": "hey"}, {"sender_raw": "Alex", "text": "hi bro"}]}],
        "Alex", gen)
    assert out["tested"] == 1 and "hi bro" not in seen["e1"]


def test_cli_and_deletion(tmp_path):
    p = _write(tmp_path)
    db = tmp_path / "cli.db"
    out = ICLI.cmd_analyze(db, str(p))
    assert "[ OK ] Parsed" in out
    names = ICLI.cmd_identities(db)
    assert "Alex" in names
    assert "Alex" in ICLI.cmd_identity(db, "Alex")
    assert ICLI.cmd_questions(db, "Alex")
    assert "[ OK ] Deleted" in ICLI.cmd_forget(db, "Alex")


def test_answer_open_and_calibrate_cli(tmp_path):
    p = _write(tmp_path)
    db = tmp_path / "cli2.db"
    ICLI.cmd_analyze(db, str(p))
    out = ICLI.cmd_answer_open(db, "Alex", "Manchester United and pizza")
    assert "[ OK ]" in out
    assert ICLI.cmd_identity(db, "Alex")  # persisted fact survives
    res = ICLI.cmd_calibrate(db, "Alex", "Chat_A", lambda ctx, eid: ("guess", "direct"))
    assert "Calibrated Alex" in res
    assert "avg composite" in res
    res2 = ICLI.cmd_calibrate(db, "Missing", "Chat_A", lambda ctx, eid: ("guess", "direct"))
    assert "Unknown identity" in res2


def test_calibrate_conversation_uses_generator_and_persists(tmp_path):
    from asis.identities import pipeline as P

    p = _write(tmp_path)
    db = tmp_path / "cal.db"
    store = IdentityStore(db)
    res = analyze_conversation(db, p, store, "Chat_A")
    cid = res["conversation_id"]
    seen: list[str] = []

    def gen(ctx, exid):
        seen.append(exid)
        return "probable next line in their voice", "direct"

    out = P.calibrate_conversation(db, cid, store, gen, target="Alex")
    assert out["status"] == "ok"
    r = out["results"]["Alex"]
    assert r["tested"] >= 1
    assert seen  # generator really invoked
    loaded = store.get(r["identity_id"])
    assert loaded is not None
    assert any(c.get("mismatch") for c in loaded.calibration)
    # analyze() with a generator auto-runs calibration without re-analysis
    res2 = analyze_conversation(db, p, store, "Chat_A", generate=gen)
    assert res2["status"] == "ok"
