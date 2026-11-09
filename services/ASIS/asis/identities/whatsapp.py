"""WhatsApp export parser + message store + progress (§5-6, §54).

Format: [DD/MM/YY, HH:MM:SS] Sender: text
Supports multiline, media placeholders, deleted, system, malformed (never
silently discarded — malformed kept with sender __malformed__).
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

HEADER_RE = re.compile(
    r"^\[(\d{1,2})/(\d{1,2})/(\d{2,4}),\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*"
    r"(AM|PM|am|pm)?\]\s*(.*?):\s?(.*)$"
)
HEADER_NODATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2,4}),.*?-\s*(.*?):\s?(.*)$")

MEDIA_HINTS = ("<media omitted>", "image omitted", "video omitted",
               "document omitted", "audio omitted", "sticker omitted")
DELETED_HINTS = ("message deleted", "you deleted this message",
                 "this message was deleted")


@dataclass
class WhatsAppMessage:
    message_id: str
    conversation_id: str
    timestamp: str
    sender_raw: str
    text: str
    media_type: str  # text|image|video|document|audio|sticker|deleted|system|malformed
    reply_reference: str | None
    sequence_index: int
    raw_source_reference: str


def _classify(text: str) -> str:
    low = text.strip().lower()
    for h in DELETED_HINTS:
        if h in low:
            return "deleted"
    for h in MEDIA_HINTS:
        if h in low:
            if "image" in low or "photo" in low:
                return "image"
            if "video" in low:
                return "video"
            if "audio" in low or "voice" in low:
                return "audio"
            if "sticker" in low:
                return "sticker"
            if "document" in low:
                return "document"
            return "image"
    return "text"


def parse_whatsapp_export(
    path: str | Path, conversation_id: str | None = None
) -> list[WhatsAppMessage]:
    """Parse full export chronologically. Never samples or skips."""
    p = Path(path)
    raw = p.read_text(encoding="utf-8", errors="replace").splitlines()
    conv = conversation_id or p.stem
    out: list[WhatsAppMessage] = []
    current_sender: str | None = None
    current_text: list[str] = []
    current_ts = ""
    current_raw: list[str] = []
    seq = 0

    def flush() -> None:
        nonlocal seq
        if current_sender is None:
            return
        text = "\n".join(current_text)
        out.append(WhatsAppMessage(
            message_id=f"{conv}:{seq:06d}",
            conversation_id=conv,
            timestamp=current_ts,
            sender_raw=current_sender,
            text=text,
            media_type=_classify(text),
            reply_reference=None,
            sequence_index=seq,
            raw_source_reference="\n".join(current_raw),
        ))
        seq += 1

    for line in raw:
        m = HEADER_RE.match(line)
        if m:
            flush()
            dd, mm, yy, hh, mi, ss, ampm, sender, text = m.groups()
            year = int(yy) if len(yy) == 4 else 2000 + int(yy)
            hour = int(hh)
            if ampm:
                a = ampm.lower()
                if a == "pm" and hour != 12:
                    hour += 12
                if a == "am" and hour == 12:
                    hour = 0
            try:
                ts = datetime(year, int(mm), int(dd), hour, int(mi),
                              int(ss or 0)).isoformat()
            except ValueError:
                ts = f"{yy}-{mm}-{dd}T{hh}:{mi}"
            current_sender = sender.strip() or "__unknown__"
            current_text = [text]
            current_ts = ts
            current_raw = [line]
        else:
            m2 = HEADER_NODATE_RE.match(line)
            if m2:
                flush()
                dd, mm, yy, sender, text = m2.groups()
                current_sender = sender.strip() or "__unknown__"
                current_text = [text]
                current_ts = f"{yy}-{mm}-{dd}"
                current_raw = [line]
            elif current_sender is not None:
                current_text.append(line)
                current_raw.append(line)
            else:
                # Malformed leading line — keep, never discard.
                out.append(WhatsAppMessage(
                    message_id=f"{conv}:{seq:06d}",
                    conversation_id=conv,
                    timestamp="",
                    sender_raw="__malformed__",
                    text=line,
                    media_type="malformed",
                    reply_reference=None,
                    sequence_index=seq,
                    raw_source_reference=line,
                ))
                seq += 1
    flush()
    return out


class ConversationStore:
    """SQLite message + progress store (persistent resume §6)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        con = self._connect()
        try:
            con.execute(
                """CREATE TABLE IF NOT EXISTS wa_messages (
                    message_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
                    timestamp TEXT, sender_raw TEXT, text TEXT,
                    media_type TEXT, reply_reference TEXT,
                    sequence_index INTEGER, raw_source_reference TEXT)"""
            )
            con.execute(
                """CREATE TABLE IF NOT EXISTS wa_progress (
                    conversation_id TEXT PRIMARY KEY, phase TEXT,
                    last_message_id TEXT, last_timestamp TEXT, status TEXT)"""
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_wa_conv ON wa_messages(conversation_id, sequence_index)")
            con.commit()
        finally:
            con.close()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    def save_messages(self, messages: list[WhatsAppMessage]) -> int:
        con = self._connect()
        try:
            con.executemany(
                "INSERT OR REPLACE INTO wa_messages VALUES (?,?,?,?,?,?,?,?,?)",
                [(m.message_id, m.conversation_id, m.timestamp, m.sender_raw,
                  m.text, m.media_type, m.reply_reference, m.sequence_index,
                  m.raw_source_reference) for m in messages],
            )
            con.commit()
        finally:
            con.close()
        return len(messages)

    def load_messages(self, conversation_id: str) -> list[dict]:
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT * FROM wa_messages WHERE conversation_id=? ORDER BY sequence_index",
                (conversation_id,),
            ).fetchall()
        finally:
            con.close()
        return [dict(r) for r in rows]

    def save_progress(self, conversation_id: str, phase: str,
                      last_message_id: str, last_timestamp: str, status: str) -> None:
        con = self._connect()
        try:
            con.execute(
                "INSERT OR REPLACE INTO wa_progress VALUES (?,?,?,?,?)",
                (conversation_id, phase, last_message_id, last_timestamp, status),
            )
            con.commit()
        finally:
            con.close()

    def load_progress(self, conversation_id: str) -> dict | None:
        con = self._connect()
        try:
            row = con.execute(
                "SELECT * FROM wa_progress WHERE conversation_id=?",
                (conversation_id,),
            ).fetchone()
        finally:
            con.close()
        return dict(row) if row else None


def import_export_file(db_path: Path, path: str | Path,
                       conversation_id: str | None = None) -> dict:
    """Streaming-friendly import: parse -> store -> progress. Returns summary."""
    cid = conversation_id or Path(path).stem
    messages = parse_whatsapp_export(path, cid)
    store = ConversationStore(db_path)
    store.save_messages(messages)
    last = messages[-1] if messages else None
    store.save_progress(cid, "imported",
                        last.message_id if last else "",
                        last.timestamp if last else "", "done")
    participants = sorted({m.sender_raw for m in messages
                           if not m.sender_raw.startswith("__")})
    return {"conversation_id": cid, "messages": len(messages),
            "participants": participants,
            "status": "imported",
            "run_id": uuid.uuid4().hex[:8]}
