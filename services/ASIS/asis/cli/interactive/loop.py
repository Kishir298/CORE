"""Persistent interactive loop (thin orchestration over AssistantApp)."""

from __future__ import annotations

import contextlib
import os
import sys
import threading
from collections.abc import Callable

from asis.cli.terminal import layout as _term_layout
from asis.cli.terminal import status as _term_status

from .commands import HELP_TEXT, parse_command
from .keys import KeyWatcher
from .persona import PersonaConsole
from .renderer import TypingRenderer
from .session import InteractiveSession

EXIT_PHRASES = frozenset({"asis shutdown"})


def _clear_screen(stream=None) -> None:
    out = stream if stream is not None else sys.stdout
    try:
        # ANSI clear works on POSIX and on modern Windows consoles
        # (Windows Terminal / conhost with virtual-terminal processing);
        # skip silently when output is redirected.
        if hasattr(out, "isatty") and not out.isatty():
            return
        out.write("\033[2J\033[H")
        out.flush()
    except Exception:
        pass


def _default_voice_poll() -> str | None:
    """Non-blocking check for a typed line while in voice mode.

    Lets the user type ``/mode text`` (or any command) without restarting.
    Returns None when nothing was typed.  Never raises, never blocks.
    """
    try:
        if not sys.stdin.isatty():
            return None
        if os.name == "nt":
            import msvcrt

            if not msvcrt.kbhit():
                return None
            line = sys.stdin.readline()
        else:
            import select

            ready, _, _ = select.select([sys.stdin], [], [], 0)
            if not ready:
                return None
            line = sys.stdin.readline()
        text = (line or "").strip()
        return text or None
    except Exception:
        return None


def run_interactive(
    app,
    pipeline=None,
    doc_store=None,
    prompt: str = "> ",
    input_fn: Callable[[str], str] | None = None,
    renderer: TypingRenderer | None = None,
    stream=None,
    cleanup: Callable[[], None] | None = None,
    max_turns: int = 0,
    voice_poll: Callable[[], str | None] | None = None,
    identities_db=None,
) -> int:
    """Run the persistent terminal until /exit, /quit, shutdown phrase or CTRL+C.

    Returns a process exit code (0 normally).  ``max_turns`` bounds the loop
    for deterministic tests (0 = infinite).
    """
    out = stream if stream is not None else sys.stdout
    ask = input_fn if input_fn is not None else (lambda p: input(p))
    render = renderer if renderer is not None else TypingRenderer(stream=out)
    session = InteractiveSession(app, pipeline=pipeline, doc_store=doc_store)
    # Multi-person identity simulation console (lazy DB access).
    session.persona_console = PersonaConsole(app, db_path=identities_db)
    stop_event = threading.Event()
    shutdown_event = threading.Event()
    poll_typed = voice_poll if voice_poll is not None else _default_voice_poll

    def _ensure_interrupts():
        interrupts = getattr(app, "interrupts", None)
        if interrupts is None:
            try:
                from asis.system.interrupt import InterruptCoordinator

                interrupts = InterruptCoordinator()
                with contextlib.suppress(Exception):
                    app.interrupts = interrupts
                    engine = getattr(app, "engine", None)
                    if (
                        engine is not None
                        and getattr(engine, "interrupts", None) is None
                    ):
                        with contextlib.suppress(Exception):
                            engine.interrupts = interrupts
                    pl = pipeline
                    if pl is not None and getattr(pl, "interrupts", None) is None:
                        with contextlib.suppress(Exception):
                            pl.interrupts = interrupts
            except Exception:
                return getattr(app, "interrupts", None)
        return interrupts

    def _reset_turn_state() -> None:
        """Start a fresh prompt: clear ESC flag and reset cancel tokens.

        One ESC poisons only the in-flight turn. Without this reset the
        next inference would immediately observe a stale cancel and abort.
        """
        stop_event.clear()
        interrupts = _ensure_interrupts()
        if interrupts is not None:
            for scope in ("inference", "voice", "tools"):
                with contextlib.suppress(Exception):
                    interrupts.register(scope)

    def _stop_audio() -> None:
        if pipeline is not None:
            with contextlib.suppress(Exception):
                tts = getattr(pipeline, "tts", None)
                if tts is not None and hasattr(tts, "stop"):
                    tts.stop()
            with contextlib.suppress(Exception):
                pipeline.audio_output.stop()

    def _cancel_scopes() -> None:
        interrupts = _ensure_interrupts()
        if interrupts is not None:
            with contextlib.suppress(Exception):
                interrupts.cancel_all()
            for scope in ("inference", "voice", "tools"):
                with contextlib.suppress(Exception):
                    interrupts.cancel(scope)

    def _on_esc() -> None:
        stop_event.set()
        _cancel_scopes()
        _stop_audio()

    def _on_shutdown() -> None:
        _cancel_scopes()
        _stop_audio()

    def _on_tab() -> None:
        """TAB: switch text <-> voice without restarting (panel UI)."""
        try:
            mode = session.toggle_mode()
        except Exception:
            return
        try:
            with contextlib.suppress(Exception):
                out.write(_term_status.status_bar(mode=mode.upper()) + "\n")
            out.flush()
        except Exception:
            pass

    def _run_cancellable(fn):
        """Run ``fn`` so ESC/SHUTDOWN returns the UI promptly.

        Blocking provider HTTP (e.g. Ollama ``requests.post``) cannot be
        safely killed mid-socket; it remains bounded by the configured
        request timeout. This waiter therefore abandons a still-running
        worker after cancellation and hands the prompt back immediately;
        the orphan is a daemon thread whose late result is discarded and
        never touches conversation/tool/terminal state.
        Returns (status, value): status in {"ok","error","cancelled","shutdown"}.
        """
        box: dict = {}

        def _target() -> None:
            try:
                box["value"] = fn()
            except BaseException as exc:  # noqa: BLE001 - transported to caller
                box["error"] = exc

        worker = threading.Thread(target=_target, daemon=True)
        worker.start()
        while worker.is_alive():
            if shutdown_event.is_set():
                _cancel_scopes()
                _stop_audio()
                return "shutdown", None
            if stop_event.is_set():
                _cancel_scopes()
                _stop_audio()
                return "cancelled", None
            worker.join(timeout=0.05)
        if shutdown_event.is_set():
            return "shutdown", None
        if stop_event.is_set():
            return "cancelled", None
        if "error" in box:
            raise box["error"]
        return "ok", box.get("value")

    def _say_goodbye() -> None:
        try:
            with contextlib.suppress(Exception):
                out.write(_term_layout.footer() + "\n")
            out.flush()
        except Exception:
            pass

    def _run_streamed_chat(message: str):
        """Run one text turn with live chunk display.

        Returns (status, response) mirroring _run_cancellable, but chunks
        appear as they arrive. Falls back to legacy render when nothing
        streamed (e.g. native direct answers, scripted mocks).
        """
        streamed: list[str] = []
        render.begin_stream()

        def _on_chunk(chunk: str) -> None:
            if stop_event.is_set() or shutdown_event.is_set():
                return
            if chunk:
                streamed.append(chunk)
                render.write_chunk(chunk)

        # Live tool badges: subscribe per turn to the app event bus (if any).
        # Handlers only write display lines; engine/tool semantics untouched.
        _tool_subs: list[tuple] = []

        def _unsub_tools() -> None:
            bus = getattr(app, "event_bus", None)
            if bus is None or not _tool_subs:
                return
            for _etype, _handler in _tool_subs:
                with contextlib.suppress(Exception):
                    bus.unsubscribe(_etype, _handler)
            _tool_subs.clear()

        def _on_tool(event) -> None:
            if stop_event.is_set() or shutdown_event.is_set():
                return
            try:
                data = getattr(event, "data", {}) or {}
                name = str(data.get("tool", "tool"))
                etype = str(getattr(event, "type", ""))
                done = "finished" in etype or "failed" in etype or "denied" in etype
                with contextlib.suppress(Exception):
                    out.write(_term_layout.tool_badge(name, done=done) + "\n")
                    out.flush()
            except Exception:
                pass

        with contextlib.suppress(Exception):
            from asis.events.events import EventType as _EventType

            _bus = getattr(app, "event_bus", None)
            if _bus is not None:
                for _etype in (
                    _EventType.TOOL_EXECUTION_STARTED,
                    _EventType.TOOL_EXECUTION_FINISHED,
                    _EventType.TOOL_EXECUTION_FAILED,
                    _EventType.TOOL_DENIED,
                ):
                    with contextlib.suppress(Exception):
                        _bus.subscribe(_etype, _on_tool)
                        _tool_subs.append((_etype, _on_tool))

        try:
            status, response = _run_cancellable(
                lambda _m=message: session.chat_text_streamed(_m, _on_chunk)
            )
        except Exception as exc:
            _unsub_tools()
            render.end_stream(interrupted=False)
            return "error", f"Sorry, that failed: {exc}"
        if status == "shutdown":
            _unsub_tools()
            render.end_stream(interrupted=True)
            return status, None
        if status == "cancelled":
            _unsub_tools()
            render.end_stream(interrupted=True)
            return status, None
        if status == "error":
            _unsub_tools()
            render.end_stream(interrupted=False)
            return status, response
        # status ok
        _unsub_tools()
        if streamed:
            render.end_stream(interrupted=False)
        else:
            # Nothing streamed (tool direct answer / empty chunks):
            # close prefix line then legacy-render full text.
            render.end_stream(interrupted=False)
            render.render(response or "", stop_event=stop_event)
            return "rendered", response
        return status, response

    def _run_persona_chat(message: str):
        """One persona-mode turn: stream the simulated identity's reply.

        No tools, no memory, no event bus: the persona says only what the
        reconstructed system prompt asks for. ESC/SHUTDOWN interrupt it like
        any other turn.
        """
        persona = session.persona_console
        streamed: list[str] = []
        render.begin_stream()

        def _on_chunk(chunk: str) -> None:
            if stop_event.is_set() or shutdown_event.is_set():
                return
            if chunk:
                streamed.append(chunk)
                render.write_chunk(chunk)

        try:
            status, reply = _run_cancellable(
                lambda: persona.chat(message, on_chunk=_on_chunk)
            )
        except Exception as exc:
            render.end_stream(interrupted=False)
            return "error", f"Sorry, that failed: {exc}"
        if status != "ok":
            render.end_stream(interrupted=True)
            return status, reply
        render.end_stream(interrupted=False)
        if not streamed:
            render.render(reply or "", stop_event=stop_event)
        return "ok", reply

    watcher = KeyWatcher(
        on_esc=_on_esc,
        on_shutdown=_on_shutdown,
        shutdown_event=shutdown_event,
        on_tab=_on_tab,
    )

    def _cleanup() -> None:
        with contextlib.suppress(Exception):
            watcher.stop()
        if cleanup is not None:
            with contextlib.suppress(Exception):
                cleanup()

    def _model_name() -> str:
        try:
            provider = getattr(app, "ai", None)
            if provider is not None and getattr(provider, "provider", None) is not None:
                value = provider.provider.model
                if value:
                    return str(value)
        except Exception:
            pass
        return "qwen3:14b"

    def _voice_state() -> str:
        return "READY" if pipeline is not None else "OFF"

    try:
        with contextlib.suppress(Exception):
            out.write(_term_layout.header(online=True) + "\n")
            out.write(
                _term_layout.status_panel(
                    model=_model_name(),
                    online=True,
                    memory=True,
                    tools=True,
                    voice=_voice_state(),
                )
                + "\n"
            )
            out.write(
                _term_layout.composer(mode=session.interaction_mode.upper()) + "\n"
            )
        out.flush()
    except Exception:
        pass
    watcher.start()
    turns = 0
    try:
        while True:
            if shutdown_event.is_set():
                _say_goodbye()
                return 0
            if max_turns and turns >= max_turns:
                return 0
            _reset_turn_state()
            try:
                if session.interaction_mode == "voice":
                    try:
                        out.write(
                            "VOICE MODE\n"
                            "Listening... (type /mode text + Enter to switch)\n"
                        )
                        out.flush()
                    except Exception:
                        pass
                    # Typed escape first: never trap the user in mic capture.
                    try:
                        typed = poll_typed()
                    except Exception:
                        typed = None
                    if not typed and voice_poll is None:
                        # Piped/scripted stdin (not a TTY): poll can't see it
                        # (msvcrt.kbhit/select only work on consoles), so
                        # consume the next scripted line instead of spinning
                        # on empty mock-audio turns forever.
                        try:
                            if not sys.stdin.isatty():
                                line = sys.stdin.readline()
                                if line == "":
                                    _say_goodbye()
                                    return 0
                                typed = (line or "").strip() or None
                        except Exception:
                            typed = None
                    if typed:
                        if typed.lower() in EXIT_PHRASES or typed.lower() in (
                            "/exit",
                            "/quit",
                        ):
                            _say_goodbye()
                            return 0
                        tcmd = parse_command(typed)
                        if tcmd is not None:
                            code = _handle_command(tcmd.name, tcmd.arg, session, out)
                            if code == "exit":
                                _say_goodbye()
                                return 0
                            turns += 1
                            continue
                        try:
                            status, response = _run_streamed_chat(typed)
                        except Exception as exc:
                            status, response = "error", f"Sorry, that failed: {exc}"
                        if status == "shutdown":
                            _say_goodbye()
                            return 0
                        if status == "cancelled":
                            turns += 1
                            continue
                        if status == "rendered":
                            turns += 1
                            continue
                        turns += 1
                        continue
                    try:
                        status, turn = _run_cancellable(session.voice_turn)
                    except RuntimeError as exc:
                        try:
                            out.write(_term_layout.assistant_bubble(str(exc)) + "\n")
                            with contextlib.suppress(Exception):
                                out.write(
                                    _term_status.clean_error(
                                        "Voice unavailable.",
                                        "voice pipeline missing",
                                        "Use /mode text to keep typing.",
                                    )
                                    + "\n"
                                )
                            out.flush()
                        except Exception:
                            pass
                        turns += 1
                        continue
                    except Exception as exc:
                        try:
                            out.write(
                                _term_layout.assistant_bubble(f"Sorry, that failed: {exc}")
                                + "\n"
                            )
                            with contextlib.suppress(Exception):
                                out.write(
                                    _term_status.clean_error(
                                        "Voice turn failed.",
                                        "see logs",
                                        "Retry or use /mode text.",
                                    )
                                    + "\n"
                                )
                            out.flush()
                        except Exception:
                            pass
                        turns += 1
                        continue
                    if status == "shutdown":
                        _say_goodbye()
                        return 0
                    if status == "cancelled":
                        try:
                            out.write(_term_layout.assistant_bubble("[interrupted]") + "\n")
                            out.flush()
                        except Exception:
                            pass
                        turns += 1
                        continue
                    if turn is None:
                        turns += 1
                        continue
                    transcript = (turn.get("transcript") or "").strip()
                    response = turn.get("response") or ""
                    if transcript:
                        try:
                            with contextlib.suppress(Exception):
                                out.write(_term_layout.user_bubble(transcript) + "\n")
                            out.flush()
                        except Exception:
                            pass
                    else:
                        turns += 1
                        continue
                    # run_once() already spoke via the existing pipeline using
                    # the same final text; render the identical transcript.
                    render.render(response, stop_event=stop_event)
                    turns += 1
                    continue
                if shutdown_event.is_set():
                    _say_goodbye()
                    return 0
                try:
                    with contextlib.suppress(Exception):
                        out.write(
                            _term_layout.composer(
                                mode=session.interaction_mode.upper(),
                                attachments=session.docs.list_names(),
                            )
                            + "\n"
                        )
                        out.flush()
                    raw = ask(prompt)
                except EOFError:
                    _say_goodbye()
                    return 0
                if shutdown_event.is_set():
                    _say_goodbye()
                    return 0
                message = (raw or "").strip()
                if not message:
                    continue
                if message.lower() in EXIT_PHRASES or message.lower() in (
                    "/exit",
                    "/quit",
                ):
                    _say_goodbye()
                    return 0
                cmd = parse_command(message)
                if cmd is not None:
                    code = _handle_command(cmd.name, cmd.arg, session, out)
                    if code == "exit":
                        _say_goodbye()
                        return 0
                    turns += 1
                    continue
                with contextlib.suppress(Exception):
                    out.write(_term_layout.user_bubble(message) + "\n")
                    out.flush()
                persona = session.persona_console
                if persona.active() is not None:
                    notice = persona.notice()
                    if notice:
                        try:
                            out.write(_term_layout.assistant_bubble(notice) + "\n")
                            out.flush()
                        except Exception:
                            pass
                    try:
                        status, response = _run_persona_chat(message)
                    except Exception as exc:
                        status, response = "error", f"Sorry, that failed: {exc}"
                else:
                    try:
                        status, response = _run_streamed_chat(message)
                    except Exception as exc:
                        status, response = "error", f"Sorry, that failed: {exc}"
                if status == "shutdown":
                    _say_goodbye()
                    return 0
                if status == "cancelled":
                    turns += 1
                    continue
                if status == "rendered":
                    turns += 1
                    continue
                if status == "error":
                    try:
                        out.write(_term_layout.assistant_bubble(str(response)) + "\n")
                        with contextlib.suppress(Exception):
                            out.write(
                                _term_status.clean_error(
                                    "Generation failed.",
                                    "provider error (see logs)",
                                    "Retry, or check Ollama with --core-status.",
                                )
                                + "\n"
                            )
                        out.flush()
                    except Exception:
                        pass
                    turns += 1
                    continue
                # status ok with live-streamed output already on screen.
                turns += 1
            except KeyboardInterrupt:
                _say_goodbye()
                return 0
    finally:
        _cleanup()
    return 0


def _make_generate(provider):
    """Build the calibration ``generate`` hook from a live AI provider.

    ``generate(context_text, exchange_id) -> (predicted_text, mode)``. The
    provider is used only for semantics; deterministic scoring lives in the
    calibration engine. Never leaks the target's reply into the prompt.
    """
    from asis.ai.models import AIMessage, MessageRole

    def generate(context: str, exchange_id: str):
        del exchange_id
        try:
            response = provider.chat(
                [
                    AIMessage(
                        role=MessageRole.SYSTEM,
                        content=(
                            "You reconstruct a WhatsApp contact's writing style. "
                            "Reply with ONLY their single next message as they "
                            "would write it — no labels, quotes or notes."
                        ),
                    ),
                    AIMessage(
                        role=MessageRole.USER,
                        content=(context or "")[:4000],
                    ),
                ]
            )
            content = getattr(response, "content", "")
            text = content if isinstance(content, str) else str(content or "")
            return text, "direct"
        except Exception:
            return "", "direct"

    return generate


def _handle_command(
    name: str, arg: str, session: InteractiveSession, out
) -> str | None:
    lname = (name or "").lower()
    if lname == "/help":
        out.write(HELP_TEXT + "\n")
        out.flush()
        return None
    if lname == "/mode":
        if not arg:
            mode = session.toggle_mode()
        elif arg.strip().lower() in ("text", "voice"):
            mode = session.set_interaction_mode(arg.strip().lower())
        else:
            out.write("Usage: /mode [text|voice]\n")
            out.flush()
            return None
        with contextlib.suppress(Exception):
            out.write(_term_status.status_bar(mode=mode.upper()) + "\n")
        out.flush()
        return None
    if lname in ("/upload", "/attach"):
        if not arg:
            out.write("Usage: /upload <path>\n")
            out.flush()
            return None
        try:
            session.docs.attach(arg)
        except FileNotFoundError:
            out.write(
                _term_layout.assistant_bubble("I couldn't find that file.") + "\n"
            )
            with contextlib.suppress(Exception):
                out.write(
                    _term_status.clean_error(
                        "Attachment failed.",
                        "file not found",
                        "Check the path and retry /upload <path>.",
                    )
                    + "\n"
                )
            out.flush()
            return None
        except ValueError as exc:
            text = str(exc)
            if "unsupported" in text.lower():
                out.write(
                    _term_layout.assistant_bubble("I can't read that file type yet.")
                    + "\n"
                )
            else:
                out.write(_term_layout.assistant_bubble(text) + "\n")
            with contextlib.suppress(Exception):
                out.write(
                    _term_status.clean_error(
                        "Attachment failed.", text[:80], "Use /docs to list supported types."
                    )
                    + "\n"
                )
            out.flush()
            return None
        except Exception as exc:
            out.write(
                _term_layout.assistant_bubble(f"Couldn't attach that file: {exc}")
                + "\n"
            )
            with contextlib.suppress(Exception):
                out.write(
                    _term_status.clean_error(
                        "Attachment failed.", "see logs", "Retry with a supported file."
                    )
                    + "\n"
                )
            out.flush()
            return None
        with contextlib.suppress(Exception):
            out.write(_term_layout.attachments_bar(session.docs.list_names()) + "\n")
        out.flush()
        return None
    if lname == "/docs":
        names = session.docs.list_names()
        with contextlib.suppress(Exception):
            out.write(_term_layout.attachments_bar(names) + "\n")
        if names:
            out.write("Use /detach <name> to remove one.\n")
        out.flush()
        return None
    if lname == "/detach":
        if not arg:
            out.write("Usage: /detach <name>\n")
            out.flush()
            return None
        if session.docs.detach(arg):
            out.write(f"Detached {arg}.\n")
        else:
            out.write(f"No attached document named {arg}.\n")
        with contextlib.suppress(Exception):
            out.write(_term_layout.attachments_bar(session.docs.list_names()) + "\n")
        out.flush()
        return None
    if lname == "/clear-docs":
        session.docs.clear()
        out.write("Cleared attached documents.\n")
        out.flush()
        return None
    if lname == "/clear":
        _clear_screen(out)
        return None
    if lname in ("/exit", "/quit"):
        return "exit"
    if lname == "/personas":
        names = session.persona_console.names()
        if not names:
            out.write(
                "No reconstructed identities yet — /identity analyze <file>.\n"
            )
        else:
            out.write("Available personas:\n")
            out.write("\n".join(f"  {n}" for n in names) + "\n")
        out.flush()
        return None
    if lname == "/persona":
        if not arg or arg.strip().lower() in ("off", "exit", "stop", "none"):
            active = session.persona_console.active()
            session.persona_console.exit()
            if active is not None:
                out.write(f"Left persona mode ({active}).\n")
            else:
                out.write("Persona mode is already off.\n")
            out.flush()
            return None
        try:
            name = session.persona_console.enter(arg)
        except KeyError:
            out.write(f"Unknown identity: {arg}. Use /personas.\n")
            out.flush()
            return None
        out.write(
            f"[persona] Simulating {name}. Replies are AI reconstructions "
            "and never ground truth.\n"
        )
        out.flush()
        return None
    if lname in ("/identities", "/identity"):
        try:
            from pathlib import Path as _P

            from asis.configuration.settings import settings as _settings
            from asis.identities import cli as _icli
            _db = _P(_settings.paths.memory) / "identities.db"
            if lname == "/identities":
                out.write(_icli.cmd_identities(_db) + "\n")
            else:
                parts = (arg or "").split(None, 2)
                sub = parts[0].lower() if parts else ""
                if sub == "analyze" and len(parts) >= 2:
                    out.write(_icli.cmd_analyze(_db, parts[1]) + "\n")
                elif sub == "answer" and len(parts) >= 3:
                    out.write(_icli.cmd_answer_open(_db, parts[1], parts[2]) + "\n")
                elif sub == "calibrate" and len(parts) >= 3:
                    provider = getattr(session.app, "ai", None)
                    provider = getattr(provider, "provider", None) if provider else None
                    if provider is None:
                        out.write("Calibration requires an AI provider "
                                  "(start with a provider, e.g. Ollama).\n")
                    else:
                        gen = _make_generate(provider)
                        out.write(_icli.cmd_calibrate(_db, parts[1], parts[2], gen) + "\n")
                elif sub in ("show", "questions", "export", "forget", "simulate") and len(parts) >= 2:
                    fn = {"show": _icli.cmd_identity, "questions": _icli.cmd_questions,
                          "export": _icli.cmd_export, "forget": _icli.cmd_forget}[sub] if sub != "simulate" else None
                    if sub == "simulate":
                        r = _icli.cmd_simulate_prompt(_db, parts[1], parts[2] if len(parts) > 2 else "hello")
                        out.write(f"Simulation [{r.get('mode')}]: {r.get('system','')[:400]}\n{r.get('notice','')}\n")
                    else:
                        r = fn(_db, parts[1])
                        out.write((r if isinstance(r, str) else str(r)) + "\n")
                else:
                    out.write("Usage: /identity analyze <file> | answer <name> <answer> | show|questions|simulate|forget|export <name> | calibrate <name> <conversation>\n")
        except Exception as exc:
            out.write(f"Identity command failed: {exc}\n")
        out.flush()
        return None
    out.write(f"Unknown command: {lname} (try /help)\n")
    out.flush()
    return None
