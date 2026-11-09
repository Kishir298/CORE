"""
Ownership-safe Ollama server lifecycle for A.S.I.S.

A.S.I.S. is HTTP-only by default: when an Ollama server is already
running it connects and claims NO ownership (external servers are never
terminated). Only a process actually started by A.S.I.S. via
``ensure_ollama()`` becomes owned, and only that exact process handle
may be stopped by ``stop_owned_ollama()``.

Never kills by executable name (no ``taskkill /IM ollama.exe``,
no ``pkill ollama`` or equivalent).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from asis.logging.logger import get_logger


class OllamaLifecycleError(RuntimeError):
    """Raised when the local Ollama server cannot be ensured or started."""


@dataclass
class OllamaOwnership:
    """Tracks whether this process owns the Ollama server.

    ``owned=True`` means ``process`` was started by this A.S.I.S. run
    and may be stopped on shutdown. ``owned=False`` means the server
    is external (or absent) and MUST be left alone.
    """

    owned: bool = False
    process: Any | None = None
    pid: int | None = None

    @property
    def is_owned_alive(self) -> bool:
        """Return True when an owned process handle is still running."""
        if not self.owned or self.process is None:
            return False
        try:
            return self.process.poll() is None
        except Exception:
            return False


def is_ollama_running(host: str, timeout: float = 5.0) -> bool:
    """Return True when ``host/api/tags`` answers (external or owned).

    Delegates to the existing Ollama provider health check so all HTTP
    stays in the provider layer (offline boundary unchanged).
    """
    try:
        from asis.ai.providers.ollama import OllamaProvider

        return bool(OllamaProvider(host=host).available(timeout=timeout))
    except Exception:
        return False


def _launch_serve(bind_host: str = "127.0.0.1:11434") -> Any:
    """Launch ``ollama serve`` detached with suppressed stdio."""
    binary = shutil.which("ollama")
    if not binary:
        raise OllamaLifecycleError(
            "Ollama is not running and no `ollama` executable was found. "
            "Install Ollama or start it manually, or set ASIS_OLLAMA_MANAGED=off."
        )
    kwargs: dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    try:
        import sys

        if sys.platform == "win32":
            # Keep the server windowless; never attach to our console.
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            kwargs["start_new_session"] = True
    except Exception:
        pass
    env = {**os.environ, "OLLAMA_HOST": bind_host}
    try:
        return subprocess.Popen([binary, "serve"], env=env, **kwargs)
    except FileNotFoundError as exc:
        raise OllamaLifecycleError(
            "Ollama is not running and `ollama serve` could not start."
        ) from exc
    except OSError as exc:
        raise OllamaLifecycleError(f"Could not start `ollama serve`: {exc}") from exc


def ensure_ollama(
    host: str,
    managed: str = "auto",
    serve_timeout: float = 60.0,
    bind_host: str = "127.0.0.1:11434",
    *,
    available_fn: Callable[[], bool] | None = None,
    popen_factory: Callable[[str], Any] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> OllamaOwnership:
    """Ensure an Ollama server is reachable, starting one only when allowed.

    - Server already up -> ``OllamaOwnership(owned=False)`` (never claimed).
    - Server down + managed in ("auto", "on") -> start ``ollama serve``,
      wait up to ``serve_timeout`` for readiness, return owned handle.
    - Server down + managed "off" (or unknown) -> raise
      ``OllamaLifecycleError``; never launch.
    - Ambiguous/unknown state defaults to NOT owned (safety first).
    """
    logger = get_logger("ai.ollama_lifecycle")
    mode = (managed or "auto").strip().lower()

    def _default_up() -> bool:
        return is_ollama_running(host)

    is_up = available_fn if available_fn is not None else _default_up
    do_sleep = sleep if sleep is not None else time.sleep

    try:
        if bool(is_up()):
            logger.info("Ollama already running (external, not owned).")
            return OllamaOwnership(owned=False)
    except Exception:
        # Treat check failure as down; proceed to managed decision.
        pass

    if mode not in ("auto", "on"):
        raise OllamaLifecycleError(
            "Ollama is not running and ASIS_OLLAMA_MANAGED=off. "
            "Start Ollama manually (`ollama serve`) or set ASIS_OLLAMA_MANAGED=auto."
        )

    factory = popen_factory if popen_factory is not None else _launch_serve
    try:
        process = factory(bind_host)
    except OllamaLifecycleError:
        raise
    except Exception as exc:
        raise OllamaLifecycleError(f"Could not start `ollama serve`: {exc}") from exc

    pid: int | None = None
    try:
        pid = int(getattr(process, "pid", 0) or 0) or None
    except Exception:
        pid = None
    ownership = OllamaOwnership(owned=True, process=process, pid=pid)
    logger.info("Started owned Ollama server (pid=%s).", pid)

    deadline = time.monotonic() + max(1.0, float(serve_timeout))
    last_error: str = ""
    while time.monotonic() < deadline:
        try:
            if bool(is_up()):
                logger.info("Owned Ollama server is reachable.")
                return ownership
        except Exception as exc:  # keep polling until the deadline
            last_error = str(exc)
        try:
            if process.poll() is not None:
                # Our own child exited early: never claim anything else.
                code = process.poll()
                raise OllamaLifecycleError(
                    f"Owned `ollama serve` exited early (code={code})."
                )
        except OllamaLifecycleError:
            _terminate_owned_quietly(ownership)
            raise
        except Exception:
            pass
        do_sleep(0.5)

    _terminate_owned_quietly(ownership)
    detail = f" {last_error}" if last_error else ""
    raise OllamaLifecycleError(
        f"Owned `ollama serve` did not become ready within "
        f"{serve_timeout:g}s.{detail}"
    )


def _terminate_owned_quietly(ownership: OllamaOwnership) -> None:
    """Best-effort terminate of an owned handle (startup-failure path)."""
    process = ownership.process
    if not ownership.owned or process is None:
        return
    try:
        with _suppress():
            process.terminate()
    except Exception:
        pass


class _suppress:
    """Minimal contextlib.suppress replacement without an import cycle."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: Any) -> bool:
        return True


def stop_owned_ollama(
    ownership: OllamaOwnership | None,
    shutdown_timeout: float = 10.0,
) -> str:
    """Stop ONLY an A.S.I.S.-owned Ollama process (bounded, verified).

    Returns one of: "unowned" (nothing to do), "stopped" (graceful),
    "forced" (terminate timed out, kill used on the owned handle),
    "unknown" (owned handle could not be verified).
    Never touches external servers.
    """
    import contextlib

    logger = get_logger("ai.ollama_lifecycle")
    if ownership is None or not ownership.owned or ownership.process is None:
        return "unowned"
    process = ownership.process
    try:
        if process.poll() is not None:
            ownership.process = None
            return "stopped"
    except Exception:
        return "unknown"

    bound = max(1.0, float(shutdown_timeout))
    with contextlib.suppress(Exception):
        process.terminate()
    try:
        process.wait(timeout=bound)
        ownership.process = None
        logger.info("Owned Ollama server stopped (pid=%s).", ownership.pid)
        return "stopped"
    except Exception:
        pass  # fall through to verified force path

    # Graceful path failed: force ONLY the owned handle we started.
    try:
        if process.poll() is None:
            with contextlib.suppress(Exception):
                process.kill()
            with contextlib.suppress(Exception):
                process.wait(timeout=5.0)
            if process.poll() is not None:
                ownership.process = None
                logger.warning("Owned Ollama force-stopped (pid=%s).", ownership.pid)
                return "forced"
            logger.error("Owned Ollama (pid=%s) would not exit.", ownership.pid)
            return "unknown"
        ownership.process = None
        return "stopped"
    except Exception:
        return "unknown"
