"""Interactive T.I.V.I.S.S. command line.

Runs the real agent pipeline (permission check → provider → memory) in a
read-eval loop. This is a thin shell over :class:`tiviss.agent.Agent`; all
behavior lives in the runtime.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any

from .. import __version__
from ..agent.agent import Agent
from ..configuration.config import ConfigValidationError, TIVISSConfig
from ..conversation.messages import Request, RequestValidationError

PROMPT = "tiviss> "

HELP_TEXT = """\
Commands:
  /help          show this help
  /clear         clear the screen (prints a separator)
  /status        show agent status
  /quit, /exit   leave the loop (Ctrl+C / Ctrl+D also work)
Anything else is sent to the agent as a request.
"""


def build_parser() -> argparse.ArgumentParser:
    """Build the ``tiviss`` command-line parser."""
    parser = argparse.ArgumentParser(
        prog="tiviss",
        description="T.I.V.I.S.S. — Though I'm Vanquished, I'm Still Stronger.",
    )
    parser.add_argument(
        "--version", action="store_true", help="print the version and exit"
    )
    parser.add_argument(
        "--message",
        default=None,
        metavar="TEXT",
        help="process a single message and exit",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="per-request provider timeout in seconds",
    )
    parser.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help="JSON config file (object with agent/model/memory/permissions keys)",
    )
    return parser


def load_config(path: str | None) -> TIVISSConfig:
    """Load configuration from a JSON file, or environment + defaults."""
    if path is None:
        return TIVISSConfig.load_env()
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigValidationError(f"cannot read config file: {exc}") from exc
    except ValueError as exc:
        raise ConfigValidationError(f"config file is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigValidationError("config file must contain a JSON object")
    return TIVISSConfig.load(raw)


def build_agent(config: TIVISSConfig) -> Agent:
    """Wire an :class:`Agent` from validated configuration."""
    policy = config.build_policy()
    # The interactive shell itself needs generate rights; deployments
    # restrict further through the configured allow/deny lists.
    policy.allow("conversation.generate")
    return Agent(
        identity=config.build_identity(),
        provider=config.build_provider(),
        memory=config.build_memory(),
        policy=policy,
    )


def _render(response) -> str:
    status = response.status.value if hasattr(response.status, "value") else str(
        response.status
    )
    if status == "ok":
        return response.content
    if status == "denied":
        return f"[denied] {response.content}"
    return f"[failed] {response.content}"


def run_once(agent: Agent, text: str, *, timeout_s: float | None = None) -> int:
    """Process one message; return a process exit code."""
    try:
        request = Request.create(source="cli", content=text)
    except RequestValidationError as exc:
        print(f"Invalid request: {exc}", file=sys.stderr)
        return 2
    response = agent.process(request, timeout_s=timeout_s)
    print(_render(response))
    return 0 if response.ok else 1


def run_loop(
    agent: Agent,
    *,
    timeout_s: float | None = None,
    prompt: str = PROMPT,
    stdin: Any = None,
    stdout: Any = None,
) -> int:
    """Read-eval loop; injectable streams make it testable."""
    inp = stdin or sys.stdin
    out = stdout or sys.stdout
    print(f"T.I.V.I.S.S. v{__version__} — type /help, /quit to leave.", file=out)
    while True:
        try:
            line = input(prompt) if inp is sys.stdin else inp.readline()
        except (EOFError, KeyboardInterrupt):
            print(file=out)
            return 0
        if inp is not sys.stdin and line == "":
            return 0
        text = (line or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in ("/quit", "/exit"):
            return 0
        if lowered == "/help":
            print(HELP_TEXT, file=out)
            continue
        if lowered == "/clear":
            print("\n" + ("-" * 40) + "\n", file=out)
            continue
        if lowered == "/status":
            status = agent.status()
            print(
                f"state={status.state.value} agent={status.agent_id} "
                f"model={status.model_id} handled={status.requests_handled}",
                file=out,
            )
            continue
        try:
            request = Request.create(source="cli", content=text)
        except RequestValidationError as exc:
            print(f"Invalid request: {exc}", file=out)
            continue
        print(_render(agent.process(request, timeout_s=timeout_s)), file=out)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Console entry point for T.I.V.I.S.S."""
    args = build_parser().parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    try:
        config = load_config(args.config)
    except ConfigValidationError as exc:
        print(f"Invalid configuration: {exc}", file=sys.stderr)
        return 2
    agent = build_agent(config)
    try:
        agent.start()
    except Exception as exc:
        print(f"Could not start agent: {exc}", file=sys.stderr)
        return 1
    try:
        if args.message is not None:
            return run_once(agent, args.message, timeout_s=args.timeout)
        return run_loop(agent, timeout_s=args.timeout)
    finally:
        with suppress(Exception):
            agent.stop()
