"""Backup tool: success/verify/failure semantics."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path


def _run(out: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/rescs_backup.py", *args],
        capture_output=True, text=True, cwd=".",
    )


def test_backup_success_and_verify(tmp_path: Path):
    src = tmp_path / "store"
    (src / "sub").mkdir(parents=True)
    (src / "a.txt").write_bytes(b"hello")
    (src / "sub" / "b.bin").write_bytes(b"world" * 100)
    (src / ".skip.tmp").write_bytes(b"nope")
    db = tmp_path / "s.db"
    c = sqlite3.connect(str(db))
    c.execute("create table t(a)")
    c.execute("insert into t values ('hi')")
    c.commit()
    c.close()
    out = tmp_path / "bak"
    r = _run(out, "--out", str(out), "--database-url", f"sqlite:///{db}", "--storage-dir", str(src), "--verify")
    assert r.returncode == 0, r.stderr
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["status"] == "ok"
    assert manifest["verified"] is True
    assert manifest["blob_count"] == 2
    paths = {f["path"] for f in manifest["files"]}
    assert paths == {"a.txt", "sub/b.bin"}
    assert all({"sha256", "size", "mtime"} <= set(f) for f in manifest["files"])
    assert manifest["db"]["sha256"]


def test_backup_missing_db_fails(tmp_path: Path):
    src = tmp_path / "store"
    src.mkdir()
    out = tmp_path / "bak"
    r = _run(out, "--out", str(out), "--database-url", "sqlite:///nope.db", "--storage-dir", str(src))
    assert r.returncode == 2
    assert "FAILED" in r.stderr


def test_backup_missing_storage_fails(tmp_path: Path):
    db = tmp_path / "s.db"
    sqlite3.connect(str(db)).close()
    out = tmp_path / "bak"
    r = _run(out, "--out", str(out), "--database-url", f"sqlite:///{db}", "--storage-dir", str(tmp_path / "absent"))
    assert r.returncode == 2


def test_backup_postgres_not_silent_success(tmp_path: Path):
    src = tmp_path / "store"
    src.mkdir()
    out = tmp_path / "bak"
    r = _run(out, "--out", str(out), "--database-url", "postgresql://u:p@localhost/db", "--storage-dir", str(src))
    assert r.returncode == 2
    assert "pg_dump" in r.stderr


def test_pg_dump_invocation_hides_password():
    import sys

    sys.path.insert(0, "scripts")
    try:
        from rescs_backup import _pg_dump_invocation
    finally:
        sys.path.remove("scripts")
    argv, env = _pg_dump_invocation("postgresql+psycopg://u:p%40ss@db:5432/app?sslmode=require")
    assert argv[0] == "pg_dump"
    assert not any("p@ss" in part for part in argv), argv
    assert argv[1].startswith("postgresql://u@db:5432/app")
    assert env is not None and env["PGPASSWORD"] == "p@ss"
    # No-password URL: no env override needed, still redacted scheme.
    argv2, env2 = _pg_dump_invocation("postgresql://u@db/app")
    assert argv2[1] == "postgresql://u@db/app"
    assert env2 is None

