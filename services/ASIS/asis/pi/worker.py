"""Text-only worker; no tools, shell, agent memory, documents or CORE uplink."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from asis.ai.models import AIMessage, MessageRole
from asis.ai.providers.ollama import OllamaProvider
from asis.pi.policy import PolicyError, enabled


def main(argv=None):
    parser = argparse.ArgumentParser(prog="asis pi-chat")
    parser.add_argument("--profile-dir", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--kind", choices=("chat", "code"), default="chat")
    parser.add_argument("--no-memory", action="store_true")
    args = parser.parse_args(argv)
    import signal
    def cancel(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, cancel)
    if not enabled():
        parser.error("set ASIS_DEPLOYMENT_PROFILE=pi to enable guarded Pi messaging")
    home = Path(args.profile_dir)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = home / ("codegen-context.json" if args.kind == "code" else "chat-context.json")
    history = []
    if not args.no_memory and path.exists():
        if path.stat().st_size > 1024 * 1024:
            raise PolicyError("Stored context exceeds its size limit")
        history = json.loads(path.read_text())[-12:]
    messages = [AIMessage(role=MessageRole.SYSTEM, content=("Return code as text only; do not claim to have executed, tested or changed files." if args.kind == "code" else "Provide general assistance as text. You have no tools or file access."))]
    for row in history:
        if row.get("role") not in ("user", "assistant") or not isinstance(row.get("content"), str):
            raise PolicyError("Invalid saved conversation")
        messages.append(AIMessage(role=MessageRole(row["role"]), content=row["content"][-8000:]))
    messages.append(AIMessage(role=MessageRole.USER, content=args.message))
    provider = OllamaProvider(model=args.model, host=os.getenv("ASIS_AI_ENDPOINT", "http://127.0.0.1:11434"), timeout=120, retries=0)
    output = []
    try:
        for chunk in provider.stream_chat(messages):
            print(chunk, end="", flush=True)
            output.append(chunk)
        print(flush=True)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"AI failed: {exc}", file=__import__('sys').stderr, flush=True)
        return 1
    if not args.no_memory:
        history.extend([{"role": "user", "content": args.message}, {"role": "assistant", "content": "".join(output)}])
        fd, name = tempfile.mkstemp(dir=home, prefix="chat-", suffix=".json")
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(history[-12:], stream)
            Path(name).replace(path)
        finally:
            Path(name).unlink(missing_ok=True)
    print("Persistence: " + ("disabled for this request" if args.no_memory else "local profile context saved; remote sync not configured"), file=__import__("sys").stderr, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
