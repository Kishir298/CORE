"""Account-to-account messaging.

This is deliberately separate from AI chat: it carries plain text between two
approved CORE accounts and never grants access to coding tools, shells, models
or privileged services. Every read and write is scoped to the authenticated
account, and the local client id doubles as the idempotency key so a retry
cannot duplicate a message.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path

MAX_BODY_BYTES = 16000
APPROVED_ROLES = ("owner", "member")


class Messages:
    def __init__(self, directory: Path, accounts):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "messages.sqlite3"
        self.accounts = accounts
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS messages(
          id TEXT PRIMARY KEY,
          sender TEXT NOT NULL,
          recipient TEXT NOT NULL,
          client_id TEXT,
          body TEXT NOT NULL,
          created REAL NOT NULL,
          delivered INTEGER NOT NULL DEFAULT 0,
          read_at REAL,
          UNIQUE(sender, client_id));
        CREATE INDEX IF NOT EXISTS messages_pair ON messages(sender, recipient, created);
        ''')
        self.db.commit()
        if os.name == "posix":
            self.path.chmod(0o600)

    # ----------------------------------------------------------- authorization
    def _recipient(self, value) -> dict:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Choose a recipient.")
        needle = value.strip()
        match = None
        for profile in self.accounts.profiles():
            if profile["id"] == needle or profile["username"] == needle.lower():
                match = profile
                break
        if match is None or match["role"] not in APPROVED_ROLES:
            # Pending, rejected and revoked accounts are not addressable.
            raise ValueError("That account is not an approved CORE account.")
        return match

    @staticmethod
    def _view(row) -> dict:
        return {
            "id": row["id"],
            "sender": row["sender"],
            "recipient": row["recipient"],
            "body": row["body"],
            "created": row["created"],
            "delivered": bool(row["delivered"]),
            "read": bool(row["read_at"]),
        }

    # ------------------------------------------------------------------ writes
    def send(self, user: dict, recipient, body, client_id: str = "") -> dict:
        if user.get("role") not in APPROVED_ROLES:
            raise PermissionError("Only approved accounts can send messages.")
        target = self._recipient(recipient)
        if target["id"] == user["id"]:
            raise ValueError("Choose another account to message.")
        if not isinstance(body, str) or not body.strip():
            raise ValueError("Write a message before sending.")
        if len(body.encode()) > MAX_BODY_BYTES:
            raise ValueError("Messages are limited to 16000 bytes.")
        key = client_id if isinstance(client_id, str) else ""
        if key and not (8 <= len(key) <= 128):
            raise ValueError("client_id must be 8-128 characters.")
        with self.lock, self.db:
            if key:
                existing = self.db.execute(
                    "SELECT * FROM messages WHERE sender=? AND client_id=?", (user["id"], key)
                ).fetchone()
                if existing is not None:
                    return self._view(existing)
            identity = uuid.uuid4().hex
            created = time.time()
            self.db.execute(
                "INSERT INTO messages VALUES(?,?,?,?,?,?,?,?)",
                (identity, user["id"], target["id"], key or None, body, created, 1, None),
            )
            row = self.db.execute("SELECT * FROM messages WHERE id=?", (identity,)).fetchone()
            return self._view(row)

    def mark_read(self, user_id: str, message_id: str) -> dict:
        with self.lock, self.db:
            row = self.db.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
            if row is None or row["recipient"] != user_id:
                raise ValueError("Message is unavailable.")
            if row["read_at"] is None:
                self.db.execute("UPDATE messages SET read_at=? WHERE id=?", (time.time(), message_id))
            return {"read": True}

    # ------------------------------------------------------------------- reads
    def conversation(self, user_id: str, peer_id: str, after: float = 0.0) -> list:
        if not isinstance(peer_id, str) or not peer_id:
            raise ValueError("Choose a conversation.")
        with self.lock, self.db:
            rows = self.db.execute(
                """SELECT * FROM messages
                   WHERE created > ? AND ((sender=? AND recipient=?) OR (sender=? AND recipient=?))
                   ORDER BY created LIMIT 500""",
                (float(after or 0), user_id, peer_id, peer_id, user_id),
            ).fetchall()
            # Opening a conversation marks the delivered messages as read.
            self.db.execute(
                "UPDATE messages SET read_at=? WHERE recipient=? AND sender=? AND read_at IS NULL",
                (time.time(), user_id, peer_id),
            )
            return [self._view(row) for row in rows]

    def threads(self, user_id: str) -> list:
        with self.lock:
            peers = self.db.execute(
                """SELECT CASE WHEN sender=? THEN recipient ELSE sender END AS peer,
                          MAX(created) AS last_at
                   FROM messages WHERE sender=? OR recipient=?
                   GROUP BY peer ORDER BY last_at DESC LIMIT 200""",
                (user_id, user_id, user_id),
            ).fetchall()
            names = {profile["id"]: profile for profile in self.accounts.profiles()}
            result = []
            for row in peers:
                last = self.db.execute(
                    """SELECT body FROM messages
                       WHERE (sender=? AND recipient=?) OR (sender=? AND recipient=?)
                       ORDER BY created DESC LIMIT 1""",
                    (user_id, row["peer"], row["peer"], user_id),
                ).fetchone()
                unread = self.db.execute(
                    "SELECT COUNT(*) FROM messages WHERE recipient=? AND sender=? AND read_at IS NULL",
                    (user_id, row["peer"]),
                ).fetchone()[0]
                profile = names.get(row["peer"], {})
                result.append({
                    "peer": row["peer"],
                    "username": profile.get("username", ""),
                    "name": profile.get("name", ""),
                    "last_body": (last["body"] if last else "")[:120],
                    "last_at": row["last_at"],
                    "unread": unread,
                })
            return result

    def close(self):
        with self.lock:
            self.db.close()
