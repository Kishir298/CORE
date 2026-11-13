"""Local authentication only. User documents and service results live in RESCS."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from pathlib import Path


class Accounts:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "accounts.sqlite3"
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT UNIQUE,
          name TEXT, role TEXT, salt TEXT, digest TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id),
          csrf TEXT, expires REAL);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at REAL, user_id TEXT,
          action TEXT, detail TEXT);
        CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id),
          name TEXT, device_type TEXT, platform TEXT, digest TEXT, created REAL,
          last_seen REAL, expires REAL, revoked INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS devices_user ON devices(user_id);
        ''')
        self.db.execute("CREATE TABLE IF NOT EXISTS password_changes(user_id TEXT PRIMARY KEY REFERENCES users(id), required INTEGER NOT NULL)")
        if 'admin_until' not in [r[1] for r in self.db.execute("PRAGMA table_info(sessions)")]:
            self.db.execute("ALTER TABLE sessions ADD COLUMN admin_until REAL NOT NULL DEFAULT 0")
        self.db.commit()
        if os.name == "posix": self.path.chmod(0o600)

    @staticmethod
    def _hash(password, salt):
        return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()

    def empty(self):
        with self.lock: return self.db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0

    def public(self, row):
        result = {k: row[k] for k in ("id", "username", "name", "role")}
        if self.must_change_password(row["id"]): result["password_change_required"] = True
        return result

    def must_change_password(self, user_id):
        with self.lock:
            row = self.db.execute("SELECT required FROM password_changes WHERE user_id=?", (user_id,)).fetchone()
            return bool(row and row[0])

    def bootstrap_owner(self, seed):
        """Import a salted verifier only into an empty database; never replace an owner."""
        username, name = seed.get("email"), seed.get("name")
        salt, digest = seed.get("salt"), seed.get("digest")
        if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_.+%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", username) or len(username)>254:
            raise ValueError("Bootstrap email is invalid.")
        if not isinstance(name, str) or not name.strip() or len(name)>80:
            raise ValueError("Bootstrap name is invalid.")
        if not isinstance(salt,str) or not re.fullmatch(r"[a-f0-9]{32}",salt) or not isinstance(digest,str) or not re.fullmatch(r"[a-f0-9]{128}",digest):
            raise ValueError("Bootstrap verifier is invalid.")
        with self.lock, self.db:
            if not self.empty(): return False
            user_id=uuid.uuid4().hex
            self.db.execute("INSERT INTO users VALUES(?,?,?,?,?,?,?)",(user_id,username.lower(),name.strip(),"owner",salt,digest,time.time()))
            self.db.execute("INSERT INTO password_changes VALUES(?,1)",(user_id,))
            return True

    def change_password(self, user_id, current, new):
        if not isinstance(current,str) or len(current)>256 or not isinstance(new,str) or not 12<=len(new)<=256:
            raise ValueError("Use a new password between 12 and 256 characters.")
        with self.lock, self.db:
            row=self.db.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone()
            if row is None or not hmac.compare_digest(self._hash(current,row["salt"]),row["digest"]):
                raise PermissionError("Current password is incorrect.")
            if hmac.compare_digest(current,new): raise ValueError("Choose a different password.")
            salt=secrets.token_hex(16)
            self.db.execute("UPDATE users SET salt=?,digest=? WHERE id=?",(salt,self._hash(new,salt),user_id))
            self.db.execute("DELETE FROM password_changes WHERE user_id=?",(user_id,))
            self.db.execute("DELETE FROM sessions WHERE user_id=?",(user_id,))
            self.db.execute("UPDATE devices SET revoked=1 WHERE user_id=?",(user_id,))

    def create(self, username, password, name, *, first=False, pending=False):
        if not isinstance(username, str) or not (re.fullmatch(r"[A-Za-z0-9_.-]{3,40}", username) or (len(username)<=254 and re.fullmatch(r"[A-Za-z0-9_.+%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", username))):
            raise ValueError("Use a valid email or a username of 3–40 letters, numbers, dots, underscores or dashes.")
        if not isinstance(password, str) or not 12 <= len(password) <= 256:
            raise ValueError("Use a password between 12 and 256 characters.")
        if not isinstance(name, str) or not name.strip() or len(name) > 80:
            raise ValueError("A display name of 1–80 characters is required.")
        salt = secrets.token_hex(16)
        digest = self._hash(password, salt)
        with self.lock:
            if first and not self.empty(): raise ValueError("Initial setup is already complete.")
            try:
                with self.db:
                    user_id = uuid.uuid4().hex
                    self.db.execute("INSERT INTO users VALUES(?,?,?,?,?,?,?)",
                                    (user_id, username.lower(), name.strip(), "owner" if first else "pending" if pending else "member", salt, digest, time.time()))
            except sqlite3.IntegrityError as exc:
                raise ValueError("Username already exists.") from exc
            return self.public(self.db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())

    def login(self, username, password):
        if not isinstance(username, str) or not isinstance(password, str) or len(password) > 256:
            raise PermissionError("Invalid username or password.")
        with self.lock:
            row = self.db.execute("SELECT * FROM users WHERE username=?", (username.lower(),)).fetchone()
            salt = row["salt"] if row else "00" * 16
            actual = self._hash(password, salt)
            if row is None or not hmac.compare_digest(actual, row["digest"]):
                raise PermissionError("Invalid username or password.")
            if row["role"] not in ("owner", "member"):
                raise PermissionError("Your access request is pending approval or was rejected. Contact the portal owner.")
            return self.issue_session(row)

    def issue_session(self, row):
        """Create a fresh 12-hour session for an already authenticated user row."""
        with self.lock:
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            with self.db:
                self.db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
                self.db.execute("INSERT INTO sessions(token,user_id,csrf,expires) VALUES(?,?,?,?)",
                                (hashlib.sha256(token.encode()).hexdigest(), row["id"], csrf, time.time()+43200))
            return token, csrf, self.public(row)

    def session(self, token):
        if not isinstance(token, str): return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            row = self.db.execute("SELECT users.*,sessions.csrf,sessions.admin_until FROM sessions JOIN users ON users.id=sessions.user_id WHERE token=? AND expires>? AND users.role IN ('owner','member')",
                                  (digest, time.time())).fetchone()
            if not row: return None
            return {**self.public(row), "csrf": row["csrf"], "admin_until": row["admin_until"]}

    def reauthenticate(self, token, password):
        if not isinstance(password,str) or len(password)>256:
            raise PermissionError("Password verification failed.")
        digest=hashlib.sha256(token.encode()).hexdigest()
        with self.lock,self.db:
            row=self.db.execute("SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id WHERE token=? AND expires>? AND role='owner'",(digest,time.time())).fetchone()
            if row is None or not hmac.compare_digest(self._hash(password,row['salt']),row['digest']):
                raise PermissionError("Password verification failed.")
            self.db.execute("UPDATE sessions SET admin_until=? WHERE token=?",(time.time()+300,digest))

    def renew_session(self, token, seconds=43200):
        if not isinstance(token, str):
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.lock, self.db:
            row = self.db.execute(
                "SELECT users.*,sessions.csrf FROM sessions JOIN users ON users.id=sessions.user_id "
                "WHERE token=? AND expires>? AND users.role IN ('owner','member')",
                (digest, time.time()),
            ).fetchone()
            if row is None:
                return None
            self.db.execute("UPDATE sessions SET expires=? WHERE token=?", (time.time()+int(seconds), digest))
            return {"profile": self.public(row), "csrf": row["csrf"], "expires_in": int(seconds)}

    def issue_device(self, user_id, name, device_type="desktop", platform=""):
        name = (name or "Desktop").strip()[:80] or "Desktop"
        device_type = (device_type or "desktop").strip().lower()[:32]
        platform = (platform or "").strip()[:120]
        if not re.fullmatch(r"[a-z0-9_.-]{1,32}", device_type):
            device_type = "desktop"
        with self.lock, self.db:
            active = self.db.execute(
                "SELECT COUNT(*) FROM devices WHERE user_id=? AND revoked=0 AND expires>?",
                (user_id, time.time()),
            ).fetchone()[0]
            if active >= 10:
                raise ValueError("This account has reached its 10-device limit. Revoke an old device first.")
            identity, secret = uuid.uuid4().hex, secrets.token_urlsafe(32)
            self.db.execute(
                "INSERT INTO devices(id,user_id,name,device_type,platform,digest,created,last_seen,expires,revoked) "
                "VALUES(?,?,?,?,?,?,?,?,?,0)",
                (identity, user_id, name, device_type, platform,
                 hashlib.sha256(secret.encode()).hexdigest(), time.time(), time.time(), time.time()+90*86400),
            )
        return {"device_id": identity, "credential": identity + "." + secret,
                "device_name": name, "device_type": device_type, "platform": platform,
                "expires_in": 90*86400}

    def device_login(self, credential):
        if not isinstance(credential, str) or len(credential) > 256 or "." not in credential:
            raise PermissionError("This device credential is not valid.")
        identity, secret = credential.split(".", 1)
        if not re.fullmatch(r"[a-f0-9]{32}", identity) or not secret:
            raise PermissionError("This device credential is not valid.")
        with self.lock, self.db:
            row = self.db.execute(
                "SELECT users.*,devices.digest AS device_digest,devices.revoked AS device_revoked,"
                "devices.expires AS device_expires FROM devices JOIN users ON users.id=devices.user_id "
                "WHERE devices.id=?", (identity,),
            ).fetchone()
            if row is None or row["device_revoked"] or row["device_expires"] <= time.time():
                raise PermissionError("This device credential has expired or was revoked.")
            if row["role"] not in ("owner", "member"):
                raise PermissionError("This account is not approved for access.")
            if not hmac.compare_digest(hashlib.sha256(secret.encode()).hexdigest(), row["device_digest"]):
                raise PermissionError("This device credential is not valid.")
            self.db.execute("UPDATE devices SET last_seen=? WHERE id=?", (time.time(), identity))
            return row

    def devices(self, user_id=None):
        query, params = "SELECT * FROM devices", []
        if user_id:
            query += " WHERE user_id=?"
            params.append(user_id)
        query += " ORDER BY last_seen DESC"
        now = time.time()
        with self.lock:
            result = []
            for row in self.db.execute(query, params):
                status = "revoked" if row["revoked"] else "expired" if row["expires"] <= now else "active"
                result.append({"device_id": row["id"], "id": row["id"], "user_id": row["user_id"],
                               "device_name": row["name"], "device_type": row["device_type"],
                               "platform": row["platform"], "created": row["created"],
                               "last_seen": row["last_seen"], "expires": row["expires"], "status": status})
            return result

    def revoke_device(self, device_id, user_id=None):
        with self.lock, self.db:
            row = self.db.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
            if row is None or (user_id and row["user_id"] != user_id):
                raise ValueError("Device not found.")
            self.db.execute("UPDATE devices SET revoked=1 WHERE id=?", (device_id,))
            return row["user_id"]

    def revoke_user_devices(self, user_id, except_id=""):
        with self.lock, self.db:
            if except_id:
                self.db.execute("UPDATE devices SET revoked=1 WHERE user_id=? AND id<>?", (user_id, except_id))
            else:
                self.db.execute("UPDATE devices SET revoked=1 WHERE user_id=?", (user_id,))

    def account_id(self, username):
        if not isinstance(username,str):raise ValueError("Account is unavailable.")
        with self.lock:
            row=self.db.execute("SELECT id FROM users WHERE username=? AND role IN ('owner','member')",(username.lower(),)).fetchone()
            if row is None:raise ValueError("Account is unavailable.")
            return row[0]

    def logout(self, token):
        with self.lock, self.db:
            self.db.execute("DELETE FROM sessions WHERE token=?", (hashlib.sha256(token.encode()).hexdigest(),))

    def register(self, username, password, name):
        with self.lock:
            if self.empty(): raise ValueError("The portal owner must finish first-run setup before public registration.")
            if self.db.execute("SELECT COUNT(*) FROM users WHERE role='pending'").fetchone()[0] >= 1000:
                raise ValueError("The portal has reached its pending-request limit.")
            return self.create(username, password, name, pending=True)

    def review(self, user_id, action):
        if action not in ("approve", "reject", "revoke"):
            raise ValueError("Choose approve, reject or revoke.")
        with self.lock, self.db:
            row = self.db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if row is None or row["role"] == "owner":
                raise ValueError("This account cannot be reviewed.")
            if action in ("approve", "reject") and row["role"] != "pending":
                raise ValueError("Only a pending request can be approved or rejected.")
            role = "member" if action == "approve" else "rejected" if action == "reject" else "pending"
            self.db.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
            self.db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            self.db.execute("UPDATE devices SET revoked=1 WHERE user_id=?", (user_id,))
            return self.public(self.db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())

    def profiles(self):
        with self.lock: return [self.public(row) for row in self.db.execute("SELECT * FROM users ORDER BY created")]

    def audit(self, user, action, detail=""):
        # Never record credentials or prompt bodies in the administrative log.
        with self.lock, self.db:
            self.db.execute("INSERT INTO audit(at,user_id,action,detail) VALUES(?,?,?,?)",
                            (time.time(), user, action, json.dumps(detail)[:300]))
            self.db.execute("DELETE FROM audit WHERE id NOT IN (SELECT id FROM audit ORDER BY id DESC LIMIT 2000)")

    def events(self):
        with self.lock: return [dict(row) for row in self.db.execute("SELECT at,user_id,action,detail FROM audit ORDER BY id DESC LIMIT 100")]

    def close(self):
        with self.lock: self.db.close()
