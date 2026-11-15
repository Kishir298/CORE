"""Create RISARMS Void Linux configuration once; never overwrite existing keys."""
from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path


def configure(base: Path, data: Path, origin: str) -> None:
    base, data = Path(base), Path(data)
    for name in ("core.env", "rescs.env", "gateway.json"):
        if (base / name).exists():
            raise SystemExit(f"Refusing to overwrite {base / name}; reconcile manually.")
    key = secrets.token_urlsafe(48)
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    core = f"""CORE_WEB_DATA={data}/core
CORE_PUBLIC_ORIGIN={origin}
CORE_EXTERNAL_STORAGE=1
CORE_SAFE_CHAT=1
CORE_MAX_AI_JOBS=1
CORE_AI_CONTEXT_LIMIT=2048
CORE_AI_THREADS=2
RISARMS_INFERENCE_LOCK=/run/risarms-inference/queue.lock
"""
    rescs = f"""RESCS_ENV=production
RESCS_REQUIRE_SIGNED_OWNER=true
RESCS_API_KEY={key}
RESCS_API_KEY_OWNER=
RESCS_DATABASE_URL=sqlite:///{data}/rescs/database/rescs.sqlite3
RESCS_STORAGE_DIR={data}/rescs/files
RESCS_AUTO_CREATE_SCHEMA=true
RESCS_MAX_FILE_SIZE=8388608
RESCS_MAX_BYTES_PER_OWNER=10737418240
RESCS_MAX_FILES_PER_OWNER=10000
RESCS_RATE_LIMIT_ENABLED=true
RESCS_RATE_LIMIT_GENERAL_PER_MINUTE=1200
RESCS_RATE_LIMIT_WRITES_PER_MINUTE=120
RESCS_RATE_LIMIT_UPLOADS_PER_MINUTE=30
TMPDIR={data}/rescs/tmp
"""
    for name, text in (("core.env", core), ("rescs.env", rescs)):
        path = base / name
        path.write_text(text)
        path.chmod(0o600)
    gateway = base / "gateway.json"
    gateway.write_text(json.dumps({
        "rescs_url": "http://127.0.0.1:8081",
        "rescs_key": key,
        "public_origin": origin,
    }, indent=2) + "\n")
    gateway.chmod(0o600)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="/etc/risarms")
    parser.add_argument("--data", default="/var/lib/risarms")
    parser.add_argument("--origin", default="https://core.local")
    args = parser.parse_args()
    configure(args.base, args.data, args.origin)
