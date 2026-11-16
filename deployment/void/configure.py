"""Create RISARMS Void Linux configuration once; never overwrite existing keys.

``/etc/risarms/gateway.json`` is the operator-facing source of truth. CORE reads
``{data}/core/gateway.json``, so both files are written from the single key in
``rescs.env`` during first-time configuration. Existing files are never rotated.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit


def _exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _validate_origin(origin: str) -> str:
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise SystemExit(f"Invalid HTTPS origin: {origin!r}")
    return origin.rstrip("/")


def _write_new(path: Path, text: str) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise SystemExit(f"Refusing to overwrite {path}; reconcile manually.") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)
    path.chmod(0o600)


def _replace(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _with_env_value(text: str, name: str, value: str) -> str:
    lines = text.splitlines()
    replacement = f"{name}={value}"
    for index, line in enumerate(lines):
        if line.partition("=")[0] == name:
            lines[index] = replacement
            break
    else:
        lines.append(replacement)
    return "\n".join(lines) + "\n"


def _rescs_key(base: Path) -> str:
    path = base / "rescs.env"
    try:
        lines = path.read_text().splitlines()
    except OSError as exc:
        raise SystemExit(f"Cannot read {path}; reconcile manually.") from exc
    for line in lines:
        name, separator, value = line.partition("=")
        if separator and name == "RESCS_API_KEY" and value:
            return value
    raise SystemExit(f"RESCS_API_KEY is missing from {path}; reconcile manually.")


def reconcile(base: Path, data: Path, origin: str | None = None) -> None:
    """Verify existing keys; adopt or repair gateways without rotating keys."""
    base, data = Path(base), Path(data)
    key = _rescs_key(base)
    canonical = base / "gateway.json"
    loaded = data / "core" / "gateway.json"
    try:
        canonical_text = canonical.read_text()
        canonical_config = json.loads(canonical_text)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Cannot read {canonical}; reconcile manually.") from exc
    if not isinstance(canonical_config, dict) or canonical_config.get("rescs_key") != key:
        raise SystemExit(f"{canonical} does not match {base / 'rescs.env'}; reconcile manually.")
    if _exists(loaded):
        try:
            loaded_config = json.loads(loaded.read_text())
        except (OSError, ValueError) as exc:
            raise SystemExit(f"Cannot read {loaded}; reconcile manually.") from exc
        if not isinstance(loaded_config, dict) or loaded_config.get("rescs_key") != key:
            raise SystemExit(f"{loaded} does not match {base / 'rescs.env'}; reconcile manually.")
    else:
        loaded.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        loaded_config = dict(canonical_config)
        _write_new(loaded, canonical_text)

    if origin is not None:
        origin = _validate_origin(origin)
        core_env = base / "core.env"
        try:
            core_text = core_env.read_text()
        except OSError as exc:
            raise SystemExit(f"Cannot read {core_env}; reconcile manually.") from exc
        if _with_env_value(core_text, "CORE_PUBLIC_ORIGIN", origin) != core_text:
            _replace(core_env, _with_env_value(core_text, "CORE_PUBLIC_ORIGIN", origin))
        for path, config in ((canonical, canonical_config), (loaded, loaded_config)):
            if config.get("public_origin") != origin:
                config["public_origin"] = origin
                _replace(path, json.dumps(config, indent=2) + "\n")


def configure(base: Path, data: Path, origin: str) -> None:
    base, data = Path(base), Path(data)
    origin = _validate_origin(origin)
    data_gateway = data / "core" / "gateway.json"
    targets = [base / name for name in ("core.env", "rescs.env", "gateway.json")]
    targets.append(data_gateway)
    for path in targets:
        if _exists(path):
            raise SystemExit(f"Refusing to overwrite {path}; reconcile manually.")
    key = secrets.token_urlsafe(48)
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    data_gateway.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
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
    gateway = json.dumps({
        "rescs_url": "http://127.0.0.1:8081",
        "rescs_key": key,
        "public_origin": origin,
    }, indent=2) + "\n"
    for path, text in (
        (base / "core.env", core),
        (base / "rescs.env", rescs),
        (base / "gateway.json", gateway),
        (data_gateway, gateway),
    ):
        _write_new(path, text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="/etc/risarms")
    parser.add_argument("--data", default="/var/lib/risarms")
    parser.add_argument("--origin", default=None)
    parser.add_argument("--reconcile", action="store_true",
                        help="verify existing configuration or adopt a missing CORE gateway")
    args = parser.parse_args()
    if args.reconcile:
        reconcile(args.base, args.data, args.origin)
    else:
        configure(args.base, args.data, args.origin or "https://core.local")
