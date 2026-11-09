"""Local-only setup and diagnostics. Network checks require an explicit flag."""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from dataclasses import asdict

from asis.configuration import settings


def run_maintenance(argv) -> int:
    parser = argparse.ArgumentParser(prog=f"asis {argv[0]}")
    if argv[0] == "setup":
        parser.add_argument("--model", default=settings.ai.model,
                            help="exact installed Ollama model name; no downloads")
    else:
        parser.add_argument("--check-model", action="store_true",
                            help="contact the configured Ollama endpoint (5 second timeout)")
        parser.add_argument("--json", action="store_true", help="machine-readable report")
    args = parser.parse_args(argv[1:])
    if argv[0] == "setup":
        if not args.model.strip() or any(c in args.model for c in '\r\n\x00'):
            parser.error("model must be a nonempty single line")
        for path in asdict(settings.paths).values():
            path.mkdir(parents=True, exist_ok=True)
        config = settings.paths.config / ".env"
        try:
            fd = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            print(f"Existing configuration preserved: {config}")
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write("ASIS_AI_PROVIDER=ollama\nASIS_AI_MODEL="
                             + json.dumps(args.model) + "\nASIS_CORE_ENABLED=false\n"
                             "ASIS_OLLAMA_MANAGED=auto\nASIS_UPDATE_CHECK_ON_STARTUP=false\n")
            print(f"Created configuration: {config}")
        print("Setup complete. No model downloaded or remote access enabled. Run asis doctor --check-model.")
        return 0

    report = {"platform": platform.system(), "python": platform.python_version(),
              "executable": sys.executable, "launcher": shutil.which("asis"),
              "provider": settings.ai.provider, "model": settings.ai.model,
              "core_enabled": settings.core.enabled,
              "persistence": "local SQLite; remote agent-state sync not configured",
              "paths": {}, "errors": [], "model_check": "not requested"}
    for name, path in asdict(settings.paths).items():
        report["paths"][name] = str(path)
        # Do not create directories or connect during an ordinary diagnosis.
        parent = path
        while not parent.exists() and parent != parent.parent:
            parent = parent.parent
        if not parent.is_dir() or not os.access(parent, os.W_OK):
            report["errors"].append(f"{name} directory is not writable")
    if args.check_model:
        if settings.ai.provider != "ollama":
            report["model_check"] = "MOCK configured; no real inference tested"
            report["errors"].append("Real Ollama provider is not selected")
        else:
            import urllib.request

            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(settings.ai.endpoint.rstrip("/") + "/api/tags", timeout=5) as response:
                    raw = response.read(1024 * 1024 + 1)
                    if len(raw) > 1024 * 1024:
                        raise ValueError("oversize model list")
                    models = json.loads(raw)["models"]
                names = {m.get("name", "") if isinstance(m, dict) else str(m) for m in models}
                requested = settings.ai.model
                found = requested in names or requested + ":latest" in names
                report["model_check"] = "installed (inference not tested)" if found else "model missing"
                if not found:
                    report["errors"].append("Configured model is not installed at the endpoint")
            except Exception:
                report["model_check"] = "unavailable"
                report["errors"].append("Model endpoint unavailable or invalid (bounded check)")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"ASIS doctor: {report['platform']} / Python {report['python']}")
        print(f"Installed launcher: {report['launcher'] or 'not on this PATH'}")
        print(f"AI: {report['provider']} / {report['model']}; check: {report['model_check']}")
        print(f"CORE: {'enabled' if report['core_enabled'] else 'disabled (standalone)'}")
        print(f"Persistence: {report['persistence']}")
        for name, path in report["paths"].items():
            print(f"{name}: {path}")
        for error in report["errors"]:
            print(f"FAIL: {error}")
    return 1 if report["errors"] else 0
