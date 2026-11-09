#!/usr/bin/env python3
"""RESCS backup: database dump + blob snapshot + verifiable manifest.

Usage:
  python scripts/rescs_backup.py --database-url sqlite:///rescs_dev.db \\
      --storage-dir rescs_storage --out backups/rescs-YYYYMMDD [--verify]

Produces (atomically via staging dir + rename):
  out/db.dump (sqlite online backup; postgres requires pg_dump, see below)
  out/blobs/ (recursive copy of object-store files, dotfiles/tmp skipped)
  out/manifest.json (sha256/size/mtime per blob, db hash, versions, counts)

Exit codes: 0 success (verified when --verify), 2 backup incomplete/failed.
Never writes secrets; manifest contains only hashes and counts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _versions() -> dict:
    versions = {"tool": "rescs_backup"}
    try:
        from rescs import __version__ as app_version

        versions["app"] = app_version
    except Exception:
        pass
    try:
        from rescs.db.schema import SchemaManager

        versions["schema"] = SchemaManager.SCHEMA_VERSION
    except Exception:
        pass
    return versions


def _url_scheme(url: str) -> str:
    # "postgresql+psycopg://..." -> "postgresql"; "sqlite:///" -> "sqlite"
    scheme = url.split(":", 1)[0]
    return scheme.split("+", 1)[0]


def _pg_dump_invocation(db_url: str) -> tuple[list[str], dict[str, str] | None]:
    """Build a pg_dump argv that never exposes the password.

    The password (if any) travels via the ``PGPASSWORD`` environment
    variable; argv carries a password-redacted URI with a libpq-native
    scheme (``postgresql://``). Raises :class:`ValueError` when no safe
    invocation can be built (never places the full URL on argv, so no
    password leaks via process listings); callers must fail closed.
    """
    from urllib.parse import unquote, urlsplit, urlunsplit

    try:
        parts = urlsplit(db_url)
    except ValueError as exc:
        raise ValueError(
            "cannot safely build pg_dump invocation: unparseable database URL "
            "(refusing to place credentials on argv)"
        ) from exc
    if not parts.hostname:
        raise ValueError(
            "cannot safely build pg_dump invocation: database URL has no host "
            "(refusing to place full URL on argv)"
        )
    netloc = parts.hostname
    if parts.port:
        netloc += f":{parts.port}"
    if parts.username:
        netloc = f"{parts.username}@{netloc}"
    clean = urlunsplit(
        (parts.scheme.split("+")[0], netloc, parts.path or "", parts.query or "", "")
    )
    env: dict[str, str] | None = None
    if parts.password:
        # urlsplit keeps percent-encoding; PGPASSWORD needs the raw value.
        env = dict(os.environ)
        env["PGPASSWORD"] = unquote(parts.password)
    return ["pg_dump", clean, "-Fc"], env


def backup_sqlite(db_path: Path, dest: Path) -> None:
    if dest.exists():
        dest.unlink()
    src = sqlite3.connect(str(db_path), timeout=30)
    dst = sqlite3.connect(str(dest), timeout=30)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    # Validate the dump opens and passes a quick integrity check.
    check = sqlite3.connect(str(dest), timeout=30)
    try:
        row = check.execute("PRAGMA integrity_check").fetchone()
        if row is None or str(row[0]).lower() != "ok":
            raise RuntimeError(f"sqlite integrity_check failed: {row!r}")
    finally:
        check.close()


def fail(out_tmp: Path, out_final: Path, message: str, manifest: dict | None = None) -> int:
    print(f"backup FAILED: {message}", file=sys.stderr)
    if manifest is not None:
        manifest["status"] = "failed"
        manifest["error"] = message
        try:
            (out_tmp / "manifest.json").write_text(json.dumps(manifest, indent=2))
            if not out_final.exists():
                os.replace(out_tmp, out_final)
        except OSError:
            pass
    else:
        shutil.rmtree(out_tmp, ignore_errors=True)
    return 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="RESCS backup tool")
    ap.add_argument("--database-url", default="sqlite:///rescs_dev.db")
    ap.add_argument("--storage-dir", default="rescs_storage")
    ap.add_argument("--out", required=True)
    ap.add_argument("--verify", action="store_true", help="re-hash dest files and fail on mismatch")
    ap.add_argument("--allow-manual-db", action="store_true",
                    help="allow non-sqlite DB without pg_dump (records hint, still exits 2)")
    args = ap.parse_args(argv)

    out_final = Path(args.out)
    if out_final.exists():
        print(f"backup FAILED: output {out_final} already exists (refusing to overwrite)", file=sys.stderr)
        return 2
    parent = out_final.parent
    parent.mkdir(parents=True, exist_ok=True)
    out_tmp = Path(tempfile.mkdtemp(prefix=out_final.name + ".tmp.", dir=str(parent)))
    blobs_out = out_tmp / "blobs"
    blobs_out.mkdir(parents=True, exist_ok=True)

    manifest: dict = {
        "created_at": datetime.now(UTC).isoformat(),
        "database_url_scheme": _url_scheme(args.database_url),
        "versions": _versions(),
        "files": [],
        "status": "ok",
    }

    # -- database ---------------------------------------------------------
    db_url: str = args.database_url
    scheme = _url_scheme(db_url)
    if scheme == "sqlite":
        raw = db_url.split("sqlite:///", 1)
        db_path = Path(raw[1] if len(raw) > 1 else "")
        if not str(db_path) or not db_path.exists():
            return fail(out_tmp, out_final, f"sqlite database not found: {db_path}", manifest)
        try:
            dest = out_tmp / "db.dump"
            backup_sqlite(db_path, dest)
            manifest["db"] = {"file": "db.dump", "sha256": _sha256_file(dest), "size": dest.stat().st_size}
        except Exception as exc:
            return fail(out_tmp, out_final, f"sqlite backup failed: {exc}", manifest)
    else:
        # Postgres and other backends require an external dump tool; never
        # pretend success without a real dump artifact.
        dumped = out_tmp / "db.dump"
        try:
            pg_argv, pg_env = _pg_dump_invocation(db_url)
        except ValueError as exc:
            # Never place the full URL (password) on argv; fail closed.
            return fail(out_tmp, out_final, f"postgres backup refused: {exc}", manifest)
        try:
            proc = subprocess.run(
                [*pg_argv, "-f", str(dumped)],
                capture_output=True, text=True, timeout=600,
                env=pg_env,
            )
        except FileNotFoundError:
            proc = None
        if proc is not None and proc.returncode == 0 and dumped.exists():
            manifest["db"] = {"file": "db.dump", "sha256": _sha256_file(dumped), "size": dumped.stat().st_size,
                              "tool": "pg_dump -Fc"}
        else:
            hint = "pg_dump $DATABASE_URL -Fc -f out/db.dump"
            detail = ""
            if proc is not None and proc.stderr:
                detail = f": {proc.stderr.strip()[:300]}"
            if args.allow_manual_db:
                manifest["db"] = {"note": "non-sqlite backend requires manual pg_dump", "hint": hint}
                return fail(out_tmp, out_final, f"postgres backup requires pg_dump{detail}", manifest)
            return fail(out_tmp, out_final,
                        f"non-sqlite backend not dumped automatically; run {hint}{detail}", manifest)

    # -- blobs (recursive, skip dotfiles/tmp) ------------------------------
    storage = Path(args.storage_dir)
    if not storage.exists():
        return fail(out_tmp, out_final, f"storage dir not found: {storage}", manifest)
    if not storage.is_dir():
        return fail(out_tmp, out_final, f"storage path is not a directory: {storage}", manifest)
    count = 0
    total_bytes = 0
    try:
        for blob in sorted(p for p in storage.rglob("*") if p.is_file()):
            rel = blob.relative_to(storage).as_posix()
            parts = rel.split("/")
            if any(part.startswith(".") for part in parts):
                continue
            if blob.name.endswith(".tmp"):
                continue
            try:
                src_hash = _sha256_file(blob)
            except OSError as exc:
                return fail(out_tmp, out_final, f"unreadable blob {rel}: {exc}", manifest)
            dest = blobs_out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(blob, dest)
            except OSError as exc:
                return fail(out_tmp, out_final, f"blob copy failed {rel}: {exc}", manifest)
            dst_hash = _sha256_file(dest)
            if dst_hash != src_hash:
                return fail(out_tmp, out_final, f"hash mismatch after copy {rel}", manifest)
            size = dest.stat().st_size
            try:
                mtime = blob.stat().st_mtime
            except OSError:
                mtime = None
            manifest["files"].append({"path": rel, "sha256": dst_hash, "size": size, "mtime": mtime})
            count += 1
            total_bytes += size
    except Exception as exc:
        return fail(out_tmp, out_final, f"blob backup failed: {exc}", manifest)
    manifest["blob_count"] = count
    manifest["total_bytes"] = total_bytes

    if args.verify:
        try:
            for entry in manifest["files"]:
                if _sha256_file(blobs_out / entry["path"]) != entry["sha256"]:
                    return fail(out_tmp, out_final, f"verify mismatch {entry['path']}", manifest)
            if manifest.get("db", {}).get("file"):
                dbf = out_tmp / manifest["db"]["file"]
                if _sha256_file(dbf) != manifest["db"]["sha256"]:
                    return fail(out_tmp, out_final, "verify mismatch db.dump", manifest)
            manifest["verified"] = True
        except OSError as exc:
            return fail(out_tmp, out_final, f"verify failed: {exc}", manifest)

    manifest["rpo"] = "daily backups: up to 24h data loss window"
    manifest["rto"] = "restore DB then blobs, verify manifest hashes; target <1h for small deployments"
    manifest["restore"] = "see docs/backups.md"
    (out_tmp / "manifest.json").write_text(json.dumps(manifest, indent=2))
    os.replace(out_tmp, out_final)
    print(f"backup complete: {count} blobs ({total_bytes} bytes) -> {out_final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

