"""
Command-line interface and console entry point for A.S.I.S.

Wires the identity, local memory, event bus and an AI provider together and
exposes a small set of subcommands: version, identity, tool listing, single
message processing, and a stdin REPL.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from asis.ai import AIManager
from asis.ai.providers import MockAIProvider
from asis.app.assistant import AssistantApp
from asis.app.modes import AssistantMode, parse_mode
from asis.configuration import settings
from asis.events import EventBus
from asis.identity import Identity, build_identity
from asis.memory import MemoryDatabase, MemoryManager, MemoryStorage
from asis.tools.provided import (
    CalculateTool,
    CurrentTimeTool,
    EchoTool,
    TranslateTextTool,
    build_core_tools,
)
from asis.update.manager import get_update_manager


def build_memory(db_path: str | Path | None = None) -> MemoryManager:
    """Build the local memory manager backed by a SQL file database."""
    from asis.errors import ConfigurationError

    if settings.memory.provider.strip().lower() != "local":
        raise ConfigurationError(
            "Invalid configuration memory.provider: only 'local' is "
            f"supported, received {settings.memory.provider!r}."
        )
    path = (
        Path(db_path)
        if db_path
        else (settings.paths.memory / settings.memory.database_name)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    return MemoryManager(MemoryStorage(MemoryDatabase(path)))


def _provider(provider_name: str, model: str):
    """Construct the requested provider, honouring the model override."""
    if provider_name == "mock":
        return MockAIProvider(model=model)
    if provider_name == "ollama":
        from asis.ai.providers import OllamaProvider, resolve_think

        return OllamaProvider(
            model=model,
            host=settings.ai.endpoint,
            timeout=settings.ai.request_timeout,
            temperature=settings.ai.temperature,
            retries=settings.network.retries,
            think=resolve_think(settings.ai.think, model),
            num_predict=settings.ai.num_predict or None,
            keep_alive=settings.ai.keep_alive or None,
        )
    raise ValueError(f"Unsupported AI provider: {provider_name}")


def build_assistant(
    identity: Identity,
    ai: AIManager,
    memory: MemoryManager,
    mode: AssistantMode | str | None = None,
    workspace: str | Path | None = None,
    core=None,
    event_bus=None,
) -> AssistantApp:
    """Build the stateful assistant owning one conversation session."""
    return AssistantApp(
        identity=identity,
        ai=ai,
        memory=memory,
        mode=mode,
        workspace=workspace,
        core=core,
        event_bus=event_bus,
    )


def core_credential() -> str | None:
    """Return the runtime-only CORE provisioning credential, if present.

    Read from ``ASIS_CORE_CREDENTIAL`` at call time; never persisted,
    never logged, never inserted into prompts or tool results. ``None``
    means standalone operation (CORE tools report ``CORE_UNAVAILABLE``).
    """
    text = (os.getenv("ASIS_CORE_CREDENTIAL") or "").strip()
    return text or None


def build_core_manager(settings_obj=None):
    """Build the optional CORE connection manager from centralized settings.

    Returns ``None`` when ``ASIS_CORE_ENABLED`` is false (standalone).
    Otherwise returns a ``CoreConnectionManager`` owning the single
    CORE-CLIENT session for this process. Callers must ``start()`` it
    (bounded, never fatal to local operation) and ``stop()`` it on
    shutdown to destroy the ephemeral session.
    """
    from asis.integrations.core.adapter import RealCoreAdapter
    from asis.integrations.core.connection import (
        build_connection_manager_from_settings,
    )

    resolved = settings_obj if settings_obj is not None else settings
    core = resolved.core
    if not core.enabled:
        return None
    adapter = RealCoreAdapter(
        host=core.host,
        port=core.port,
        device_file=core.device_file,
        ca_file=core.ca_file,
        insecure=core.insecure,
        connect_timeout=core.connect_timeout,
        request_timeout=core.request_timeout,
    )
    return build_connection_manager_from_settings(
        resolved, adapter, credential_provider=core_credential
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the ``asis`` command-line parser."""
    parser = argparse.ArgumentParser(
        prog="asis",
        description="A.S.I.S. - A Smart Intelligence System. "
        "Speak to an always-on personal assistant that remembers you.",
    )
    parser.add_argument(
        "--version", action="store_true", help="print the version and exit"
    )
    parser.add_argument(
        "--identify",
        action="store_true",
        help="print the configured identity (system prompt) and exit",
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
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="list the built-in tools and exit",
    )
    parser.add_argument(
        "--core-status",
        action="store_true",
        help="print the C.O.R.E. connection status and exit",
    )
    parser.add_argument(
        "--message",
        default=None,
        metavar="TEXT",
        help="process a single message and exit",
    )
    parser.add_argument(
        "--mode",
        default=settings.coding.default_mode,
        choices=["general", "coding", "translation"],
        help="assistant mode to use (default: %(default)s)",
    )
    parser.add_argument(
        "--workspace",
        default=None,
        metavar="PATH",
        help="coding workspace root (default: configured workspace or CWD)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="enable verbose debug logging (default: quiet in interactive mode)",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        metavar="LEVEL",
        help="log level override (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    parser.add_argument(
        "--preview", "--dry-run",
        action="store_true",
        help="render the CLI interface layout and exit (no model, no boot)",
    )
    parser.add_argument(
        "--tui",
        action="store_true",
        help="launch the Textual TUI interface (alternate-screen)",
    )
    parser.add_argument(
        "--ai-temperature",
        type=float,
        help="Set AI temperature (forwarded to TUI)",
    )
    parser.add_argument(
        "--ai-think",
        choices=["auto", "true", "false"],
        help="Set AI think mode (forwarded to TUI)",
    )
    parser.add_argument(
        "--ai-num-predict",
        type=int,
        help="Set max tokens to predict (forwarded to TUI)",
    )
    parser.add_argument(
        "--ai-keep-alive",
        type=str,
        help="Set model keep-alive duration (forwarded to TUI)",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="check for updates and optionally install them",
    )
    parser.add_argument(
        "--update-install",
        action="store_true",
        help="install available updates (requires --update)",
    )
    return parser


def handle_update(install: bool = False) -> int:
    """Handle the --update command."""

    print("Checking for updates...")
    manager = get_update_manager()
    result = manager.check_all()

    print(f"Online: {'Yes' if result.online else 'No'}")
    print(f"Last check: {result.timestamp}")

    if not result.has_updates:
        print("No updates available.")
        return 0

    print("\nAvailable updates:")
    for name in result.updatable_components:
        component = result.components[name]
        print(f"  {name}: {component.current_version} -> {component.available_version}")
        if component.description:
            print(f"    {component.description}")

    if install:
        print("\nInstalling updates...")
        install_results = manager.auto_install(result)
        for name, success in install_results.items():
            status = "OK" if success else "FAILED"
            print(f"  {name}: {status}")
        if all(install_results.values()):
            print("\nAll updates installed successfully.")
            if any(r.requires_restart for r in manager._installers.values() if hasattr(r, 'requires_restart')):
                print("Note: Some updates require ASIS restart.")
        else:
            print("\nSome updates failed to install.")
            return 1

    return 0


def core_status_line() -> str:
    """Describe the configured C.O.R.E. uplink without connecting.

    Never prompts for the provisioning credential and never opens a
    socket: with no credential available the manager reports DISABLED
    (CORE off) or DISCONNECTED (CORE on, no session) -- both secret-free.
    """
    from asis.integrations.core.adapter import RealCoreAdapter
    from asis.integrations.core.connection import (
        build_connection_manager_from_settings,
    )
    from asis.system.context import RuntimeContext

    core = settings.core
    adapter = RealCoreAdapter(
        host=core.host,
        port=core.port,
        device_file=core.device_file,
        ca_file=core.ca_file,
        insecure=core.insecure,
        connect_timeout=core.connect_timeout,
        request_timeout=core.request_timeout,
    )
    manager = build_connection_manager_from_settings(
        settings, adapter, credential_provider=None
    )
    context = RuntimeContext()
    manager.start(context)
    try:
        status = manager.status()
    finally:
        manager.stop(context)
    state = getattr(status.state, "value", str(status.state)).lower()
    if state == "disabled":
        return "CORE: disabled (standalone)."
    return f"CORE: {state} (host={core.host}:{core.port})."


def handle_mode_command(app: AssistantApp, message: str) -> str | None:
    """Handle /mode, /ascs, /translate and translation REPL commands."""
    text = message.strip()
    lowered = text.lower()
    if lowered == "/ascs":
        app.set_mode(AssistantMode.CODING)
        return f"A.S.C.S. coding mode enabled.\nWorkspace: {app.workspace.root}"
    if lowered == "/translate":
        app.set_mode(AssistantMode.TRANSLATION)
        return (
            "Translation mode enabled "
            f"(source={app.translation_source}, target={app.translation_target})."
        )
    if lowered == "/mode":
        return f"Current mode: {app.mode.value}"
    if lowered.startswith("/mode "):
        try:
            app.set_mode(parse_mode(text.split(None, 1)[1]))
        except ValueError as exc:
            return str(exc)
        if app.mode is AssistantMode.CODING:
            return f"A.S.C.S. coding mode enabled.\nWorkspace: {app.workspace.root}"
        if app.mode is AssistantMode.TRANSLATION:
            return (
                "Translation mode enabled "
                f"(source={app.translation_source}, target={app.translation_target})."
            )
        return "A.S.I.S. general mode enabled."
    if lowered.startswith("/tr-to "):
        try:
            _, target = app.set_translation_languages(target=text.split(None, 1)[1])
        except ValueError as exc:
            return str(exc)
        return f"Translation target: {target}."
    if lowered.startswith("/tr-from "):
        try:
            source, _ = app.set_translation_languages(source=text.split(None, 1)[1])
        except ValueError as exc:
            return str(exc)
        return f"Translation source: {source}."
    return None


def handle_message(
    identity: Identity,
    ai: AIManager,
    memory: MemoryManager,
    message: str,
    assistant: AssistantApp | None = None,
) -> str:
    """Process one user message through the stateful assistant pipeline.

    When ``assistant`` is provided the call joins its owned conversation
    session; otherwise a single-turn assistant is used (backwards
    compatible for direct callers and tests).
    """
    app = assistant or AssistantApp(identity=identity, ai=ai, memory=memory)
    return app.chat(message)


def _normalize_argv(raw: Sequence[str] | None) -> list[str]:
    """Return a clean argument list for the ``asis`` entry point.

    Some Windows console-script launchers prepend the executable path as
    ``sys.argv[0]`` *and* duplicate it into ``sys.argv[1]``.  When that
    happens the first user argument looks like ``...asis.exe`` and breaks
    ``argparse``.  Drop exactly one such leading launcher artifact; normal
    invocations (including ``python -m asis``) are untouched.
    """
    items = list(raw) if raw is not None else sys.argv[1:]
    if not items:
        return items
    first = items[0].replace("\\", "/").lower()
    base = first.rsplit("/", 1)[-1]
    if base in ("asis", "asis.exe", "asis.py", "__main__.py"):
        return items[1:]
    return items


def apply_cli_log_level(args) -> None:
    """Apply log-level overrides for this CLI invocation.

    Interactive/single-shot sessions default to a quiet console (WARNING)
    so normal use stays clean (no ``[INFO] Sending tool-enabled
    request...`` spam).  ``--debug`` forces DEBUG everywhere;
    ``--log-level`` forces an explicit console level.  File logging is
    preserved at the configured level; only console noise is reduced.

    Must run before any ``get_logger`` call takes effect AND after, since
    ``configure_logging()`` (re)creates handlers from settings and would
    otherwise reset the console level back to INFO.
    """
    import logging
    from logging.handlers import RotatingFileHandler

    from asis.logging.logger import configure_logging

    if getattr(args, "debug", False):
        console_level = logging.DEBUG
        file_level = logging.DEBUG
    elif getattr(args, "log_level", None):
        console_level = getattr(logging, str(args.log_level).upper(), None)
        if not isinstance(console_level, int):
            console_level = logging.WARNING
        file_level = console_level
    else:
        console_level = logging.WARNING
        file_level = getattr(
            logging, str(settings.runtime.log_level).upper(), logging.INFO
        )
        if not isinstance(file_level, int):
            file_level = logging.INFO

    # Ensure handlers exist before adjusting them.
    configure_logging()
    root = logging.getLogger("asis")
    # Root must allow the lowest level through; handlers filter the rest.
    root.setLevel(min(console_level, file_level))
    for handler in root.handlers:
        try:
            if isinstance(handler, RotatingFileHandler):
                handler.setLevel(file_level)
            else:
                handler.setLevel(console_level)
        except Exception:
            with contextlib.suppress(Exception):
                handler.setLevel(console_level)


def _build_interactive_pipeline():
    """Build the shared voice pipeline for the interactive session.

    Reuses the existing voice factory; falls back to scriptable mocks so
    the terminal works with zero audio hardware or heavy dependencies.
    Never raises: worst case returns a fully-mocked pipeline.
    """
    try:
        from asis.voice import factory as vf
        from asis.voice.pipeline import VoicePipeline

        def _try(make, fallback):
            try:
                return make()
            except Exception:
                return fallback()

        from asis.voice.engines.mock import (
            MockAudioInput,
            MockAudioOutput,
            MockSpeakerIdentifier,
            MockSpeechRecognizer,
            MockTextToSpeech,
            MockVadDetector,
        )

        pipeline = VoicePipeline(
            audio_input=_try(vf.create_audio_input, lambda: MockAudioInput([])),
            speech_recognizer=_try(vf.create_speech_recognizer, MockSpeechRecognizer),
            speaker_identifier=_try(
                vf.create_speaker_identifier, MockSpeakerIdentifier
            ),
            tts=_try(vf.create_tts, MockTextToSpeech),
            audio_output=_try(vf.create_audio_output, MockAudioOutput),
            vad=_try(vf.create_vad, MockVadDetector),
        )
        with contextlib.suppress(Exception):
            pipeline.audio_input.start()
        return pipeline
    except Exception:
        return None


def entry(argv: Sequence[str] | None = None) -> int:
    """Console entry point for A.S.I.S."""
    raw = _normalize_argv(argv)
    if raw and raw[0] == "voice":
        from asis.cli.voice import run_voice

        return run_voice(raw[1:])
    if raw and raw[0] == "translate":
        from asis.cli.translate import run_translate

        return run_translate(raw[1:])
    if raw and raw[0] == "calculate":
        from asis.cli.calculate import run_calculate

        return run_calculate(raw[1:])
    if raw and raw[0] == "tui":
        from asis.tui.__main__ import entry as tui_entry
        return tui_entry(raw[1:])

    args = build_parser().parse_args(raw)
    apply_cli_log_level(args)

    if args.tui:
        from asis.tui.__main__ import entry as tui_entry
        # Forward all relevant args to TUI
        tui_argv = []
        if args.provider:
            tui_argv.extend(["--provider", args.provider])
        if args.model:
            tui_argv.extend(["--model", args.model])
        if args.ai_temperature is not None:
            tui_argv.extend(["--ai-temperature", str(args.ai_temperature)])
        if args.ai_think is not None:
            tui_argv.extend(["--ai-think", args.ai_think])
        if args.ai_num_predict is not None:
            tui_argv.extend(["--ai-num-predict", str(args.ai_num_predict)])
        if args.ai_keep_alive is not None:
            tui_argv.extend(["--ai-keep-alive", args.ai_keep_alive])
        return tui_entry(tui_argv)

    if args.version:
        print(f"{settings.app_name} {settings.app_version}")
        return 0

    if args.identify:
        print(build_identity().system_prompt())
        return 0

    if args.list_tools:
        for tool in (
            EchoTool(),
            CurrentTimeTool(),
            CalculateTool(),
            TranslateTextTool(),
            *build_core_tools(None),
        ):
            print(f"{tool.name}: {tool.description}")
        return 0

    if args.core_status:
        print(core_status_line())
        return 0

    if args.update:
        return handle_update(args.update_install)

    if args.preview:
        from asis.cli.terminal import layout as _term_layout

        w = _term_layout.terminal_width()
        model = getattr(settings.ai, "model", "qwen3:14b")
        print(_term_layout.header(online=True))
        print(_term_layout.status_panel(model=model, online=True, memory=True, tools=True, voice="READY"))
        print(_term_layout.composer(mode="TEXT", attachments=[]))
        print(_term_layout.bottom_strip(mode="TEXT", model=model, ollama=True, memory=True, tools=True, voice="READY"))
        print(_term_layout.footer(w))
        return 0

    identity = build_identity()
    provider = _provider(args.provider, args.model)
    event_bus = EventBus()
    ai = AIManager(provider=provider, event_bus=event_bus)
    memory = build_memory(args.memory_db)

    # Ollama lifecycle ownership: connect when already running (never
    # owned), optionally start an owned `ollama serve` when down.
    # Only the exact process started here may be stopped on shutdown.
    from asis.ai.ollama_lifecycle import (
        OllamaLifecycleError,
        OllamaOwnership,
        ensure_ollama,
        stop_owned_ollama,
    )

    ollama_ownership = OllamaOwnership(owned=False)
    if args.provider == "ollama":
        try:
            # Extract bind host from endpoint for managed server
            from urllib.parse import urlparse
            parsed = urlparse(settings.ai.endpoint)
            bind_host = f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname
            if not bind_host or bind_host in ("127.0.0.1", "localhost"):
                bind_host = "127.0.0.1:11434"
            
            ollama_ownership = ensure_ollama(
                settings.ai.endpoint,
                managed=settings.ollama.managed,
                serve_timeout=settings.ollama.serve_timeout,
                bind_host=bind_host,
            )
        except OllamaLifecycleError as exc:
            print(f"[FAIL] Ollama unavailable: {exc}")
            return 1

    # Optional CORE uplink: one manager, one adapter, one connection for
    # this process. Disabled/unreachable -> standalone; local chat, memory,
    # tools, A.S.C.S. and voice paths are unaffected.
    from asis.system.context import RuntimeContext

    core_manager = build_core_manager()
    core_ctx: RuntimeContext | None = None

    pipeline = None

    def _shutdown_owned_ollama() -> None:
        with contextlib.suppress(Exception):
            stop_owned_ollama(
                ollama_ownership,
                shutdown_timeout=settings.ollama.shutdown_timeout,
            )

    def _shutdown_core() -> None:
        if core_manager is not None and core_ctx is not None:
            with contextlib.suppress(Exception):
                core_manager.stop(core_ctx)

    try:
        if core_manager is not None:
            core_ctx = RuntimeContext()
            core_manager.start(core_ctx)

        app = build_assistant(
            identity,
            ai,
            memory,
            mode=args.mode,
            workspace=args.workspace,
            core=core_manager,
            event_bus=event_bus,
        )

        # Boot sequence + silent model readiness probe. Real inference
        # only; failure never enters interactive mode. Owned Ollama is
        # cleaned up on boot failure via the outer finally.
        from asis.app.boot import BootError, run_boot_sequence

        try:
            run_boot_sequence(
                identity, memory, app, provider, ollama_ownership
            )
        except BootError as exc:
            print(f"[FAIL] Boot failed: {exc}")
            return 1
        except KeyboardInterrupt:
            print("\nBoot cancelled.")
            return 130

        if args.message is not None:
            try:
                print(handle_message(identity, ai, memory, args.message, assistant=app))
            except KeyboardInterrupt:
                return 130
            return 0

        # Persistent interactive terminal (TEXT/VOICE, docs, typing effect).
        from asis.cli.interactive import run_interactive
        from asis.documents import DocumentStore

        pipeline = _build_interactive_pipeline()

        def _cleanup() -> None:
            if pipeline is not None:
                with contextlib.suppress(Exception):
                    pipeline.stop()
            _shutdown_core()

        try:
            return run_interactive(
                app, pipeline=pipeline, doc_store=DocumentStore(), cleanup=_cleanup
            )
        except KeyboardInterrupt:
            return 130
        finally:
            # run_interactive already ran _cleanup; guard double-stop above.
            pass
    except KeyboardInterrupt:
        return 130
    finally:
        # Centralized shutdown (every exit path): pipeline, CORE, then
        # ONLY an A.S.I.S.-owned Ollama process (external servers untouched).
        if pipeline is not None:
            with contextlib.suppress(Exception):
                pipeline.stop()
        _shutdown_core()
        _shutdown_owned_ollama()
    return 0


if __name__ == "__main__":
    raise SystemExit(entry())
