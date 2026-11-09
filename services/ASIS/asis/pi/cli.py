"""Owner diagnostics without downloads, prompts or account content."""
import argparse
import json

from .policy import Snapshot, approval, snapshot
from .runtime import queue_directory


def status(argv=None):
    parser = argparse.ArgumentParser(prog="asis pi-status")
    parser.add_argument("--model")
    parser.add_argument("--sample", action="store_true", help="sample CPU for 10 seconds and check admission locally")
    args = parser.parse_args(argv)
    report = {"status": "unconfigured", "reason": "no queued job yet; no inference performed"}
    file = queue_directory() / "status.json"
    if file.exists():
        report = json.loads(file.read_text())
    if args.sample:
        from dataclasses import asdict
        report = {"status": "diagnostic", "resources": asdict(snapshot())}
        if args.model:
            from .policy import decide
            record, peak, _ = approval(args.model)
            report = decide(Snapshot(**report["resources"]), record, peak)
            report["model"] = args.model
    print(json.dumps(report, indent=2))
    return 1 if report["status"] in ("blocked", "failed") else 0
