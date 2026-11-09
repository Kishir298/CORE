"""
``asis translate`` subcommand: offline translation REPL/single-shot.

Runs the shared AssistantApp in TRANSLATION mode (same runtime, same
router/permission path as every other mode). Supports ``/tr-to``,
``/tr-from``, and ``/mode`` REPL commands.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from asis.app.modes import AssistantMode
from asis.configuration.settings import settings


def build_translate_parser() -> argparse.ArgumentParser:
    """Build the ``asis translate`` command-line parser."""
    parser = argparse.ArgumentParser(
        prog="asis translate",
        description="A.S.I.S. offline translation (local model, no internet).",
    )
    parser.add_argument(
        "--to",
        default=settings.translation.default_target,
        metavar="LANG",
        help="target language code (default: %(default)s)",
    )
    parser.add_argument(
        "--from",
        dest="source",
        default=settings.translation.default_source,
        metavar="LANG",
        help="'auto' or source language code (default: %(default)s)",
    )
    parser.add_argument(
        "--message",
        default=None,
        metavar="TEXT",
        help="translate a single message and exit",
    )
    parser.add_argument(
        "--provider",
        default=settings.ai.provider,
        choices=["mock", "ollama"],
        help="AI provider to use (default: %(default)s)",
    )
    parser.add_argument(
        "--model",
        default=settings.ai.model,
        help="model to use (default: %(default)s)",
    )
    parser.add_argument(
        "--memory-db",
        default=None,
        metavar="PATH",
        help="file for the local memory database (default: configured path)",
    )
    return parser


def run_translate(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``asis translate``."""
    from asis.ai import AIManager
    from asis.cli.main import (
        _provider,
        build_assistant,
        build_memory,
        handle_mode_command,
    )
    from asis.identity import build_identity

    args = build_translate_parser().parse_args(argv)
    identity = build_identity()
    ai = AIManager(provider=_provider(args.provider, args.model))
    memory = build_memory(args.memory_db)
    app = build_assistant(identity, ai, memory, mode=AssistantMode.TRANSLATION)
    try:
        app.set_translation_languages(source=args.source, target=args.to)
    except ValueError as exc:
        print(str(exc))
        return 2

    if args.message is not None:
        print(app.chat(args.message))
        return 0

    print(identity.greeting)
    print(
        "Translation mode "
        f"(source={app.translation_source}, target={app.translation_target})."
    )
    shutdown = settings.identity.shutdown_phrase.lower()
    for raw in sys.stdin:
        message = raw.strip()
        if not message:
            continue
        if message.lower() == shutdown:
            print("Shutting down.")
            return 0
        handled = handle_mode_command(app, message)
        if handled is not None:
            print(handled)
            continue
        print(app.chat(message))
    return 0
