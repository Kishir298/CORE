"""
A.S.I.S. boot sequence + silent model readiness probe.

Boot reflects real state: every ``[ OK ]`` line is emitted only after
the corresponding subsystem verified. The readiness probe sends a
single internal ``hello`` directly through the existing provider
instance (no ConversationSession, no ContextAssembler, no memory,
no documents, no tools) and discards the response. It never enters
conversation history, memory, transcripts, or terminal output.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from asis.ai.models import AIMessage, MessageRole
from asis.configuration import settings
from asis.logging.logger import get_logger

PROBE_TEXT = "hello"


@dataclass(frozen=True)
class ReadinessPolicy:
    """Configuration for the model readiness probe."""

    overall_timeout_s: float = 120.0
    probe_num_predict: int = 32
    probe_think: bool = False
    require_visible: bool = True

    @classmethod
    def from_settings(cls) -> "ReadinessPolicy":
        """Create policy from global settings."""
        br = settings.boot_readiness
        return cls(
            overall_timeout_s=float(br.timeout),
            probe_num_predict=br.probe_num_predict,
            probe_think=not br.disable_think,
            require_visible=br.require_visible,
        )


class BootError(RuntimeError):
    """Raised when any boot stage (including model readiness) fails."""


@dataclass
class BootStage:
    """One boot line: label shown only after its check passes."""

    label: str
    duration_ms: float = 0.0
    ok: bool = False


@dataclass
class BootReport:
    """Ordered boot stages plus probe timing (no probe content stored)."""

    stages: list[BootStage] = field(default_factory=list)
    probe_ms: float = 0.0
    probe_chars: int = 0
    ollama_owned: bool = False


def verify_model_readiness(provider: object, policy: ReadinessPolicy | None = None) -> tuple[int, float]:
    """Send the silent ``hello`` probe via the SAME provider instance.

    Returns ``(response_chars, elapsed_ms)``. Raises ``BootError`` when
    the model does not produce a valid non-empty response.

    Lightweight by construction: exactly one USER message, no system
    prompt, no tools, no history. For Ollama-backed providers the
    probe temporarily forces ``think=False`` and a small
    ``num_predict`` on the existing instance (restored afterwards);
    other providers are called untouched.
    """
    if policy is None:
        policy = ReadinessPolicy.from_settings()

    logger = get_logger("app.boot")
    messages = [AIMessage(role=MessageRole.USER, content=PROBE_TEXT)]

    # Reuse the instance (no second client): patch lightweight attrs only.
    saved: dict[str, object] = {}
    for attr, value in (("think", policy.probe_think), ("num_predict", policy.probe_num_predict), ("timeout", policy.overall_timeout_s)):
        try:
            if hasattr(provider, attr):
                saved[attr] = getattr(provider, attr)
                setattr(provider, attr, value)
        except Exception:
            continue

    started = time.monotonic()
    try:
        chat = getattr(provider, "chat", None)
        if not callable(chat):
            raise BootError("AI provider has no chat() method.")
        response = chat(messages)
        content = getattr(response, "content", "")
        text = content if isinstance(content, str) else str(content or "")
        if policy.require_visible and not text.strip():
            raise BootError("Model readiness probe returned an empty response.")
        elapsed_ms = (time.monotonic() - started) * 1000.0
        logger.debug(
            "Model readiness probe ok (%d chars, %.0fms).",
            len(text),
            elapsed_ms,
        )
        return len(text), elapsed_ms
    except BootError:
        raise
    except Exception as exc:
        raise BootError(f"Model readiness probe failed: {exc}") from exc
    finally:
        for attr, value in saved.items():
            try:
                setattr(provider, attr, value)
            except Exception:
                continue


def _write(out: object, text: str) -> None:
    try:
        write = getattr(out, "write", None)
        if callable(write):
            write(text)
            flush = getattr(out, "flush", None)
            if callable(flush):
                flush()
    except Exception:
        pass


def run_boot_sequence(
    identity: object,
    memory: object,
    app: object,
    provider: object,
    ollama_ownership: object = None,
    out: object | None = None,
    probe_fn: Callable[[object], tuple[int, float]] | None = None,
) -> BootReport:
    """Run the blocking boot sequence; raise ``BootError`` on any failure.

    Prints the banner + one line per verified stage. The probe itself
    (``hello`` + model reply) is never written to ``out`` and never
    stored on ``app.session``/memory.
    """
    stream = out if out is not None else sys.stdout
    report = BootReport()
    owned = bool(getattr(ollama_ownership, "owned", False))
    report.ollama_owned = owned

    _write(stream, "A.S.I.S.\n")
    _write(stream, "--------------------------------\n")
    _write(stream, "[BOOT] Starting A.S.I.S.\n")

    def _stage(label: str, check: Callable[[], None]) -> None:
        started = time.monotonic()
        try:
            check()
        except BootError:
            raise
        except Exception as exc:
            raise BootError(f"{label} failed: {exc}") from exc
        elapsed_ms = (time.monotonic() - started) * 1000.0
        report.stages.append(BootStage(label=label, duration_ms=elapsed_ms, ok=True))
        _write(stream, f"[ OK ] {label}\n")

    from asis.configuration.settings import settings as global_settings

    def _check_config() -> None:
        if not getattr(global_settings, "app_name", ""):
            raise BootError("Configuration failed: app_name is empty.")

    def _check_identity() -> None:
        name = getattr(identity, "name", "")
        if not isinstance(name, str) or not name.strip():
            raise BootError("Identity failed: name is empty.")
        try:
            prompt = identity.system_prompt()  # type: ignore[attr-defined]
        except Exception as exc:
            raise BootError(f"Identity failed: {exc}") from exc
        if not str(prompt or "").strip():
            raise BootError("Identity failed: system prompt is empty.")

    def _check_personality() -> None:
        personality = getattr(identity, "personality", "")
        if not isinstance(personality, str) or not personality.strip():
            raise BootError("Personality failed: personality text is empty.")

    def _check_memory() -> None:
        if memory is None or getattr(memory, "storage", None) is None:
            raise BootError("Memory failed: local memory is unavailable.")

    def _check_tools() -> None:
        router = getattr(app, "tools_router", None)
        registry = getattr(router, "registry", None)
        list_names = getattr(registry, "list_names", None)
        if not callable(list_names):
            raise BootError("Tools failed: tool registry is unavailable.")
        try:
            names = list(list_names())
        except Exception as exc:
            raise BootError(f"Tools failed: {exc}") from exc
        if not names:
            raise BootError("Tools failed: no tools registered.")

    def _check_ollama() -> None:
        available = getattr(provider, "available", None)
        if callable(available):
            try:
                up = available(timeout=5.0)
            except TypeError:
                up = available()
            except Exception as exc:
                raise BootError(f"Ollama failed: {exc}") from exc
            if not up:
                raise BootError("Ollama server is not reachable.")
        elif ollama_ownership is None:
            raise BootError("Ollama failed: provider has no availability check.")

    _stage("Configuration loaded", _check_config)
    _stage("Identity loaded", _check_identity)
    _stage("Personality loaded", _check_personality)
    _stage("Memory initialized", _check_memory)
    _stage("Tools initialized", _check_tools)
    _stage("Ollama ready", _check_ollama)

    _write(stream, "[....] Verifying model...\n")
    started = time.monotonic()
    policy = ReadinessPolicy.from_settings()
    if probe_fn is not None:
        # Legacy custom probe - wrap to maintain compatibility
        def wrapped_probe(p):
            return probe_fn(p)
        probe = wrapped_probe
    else:
        def default_probe(p):
            return verify_model_readiness(p, policy)
        probe = default_probe
    try:
        chars, probe_ms = probe(provider)
    except BootError as exc:
        _write(stream, f"[FAIL] Model readiness check failed: {exc}\n")
        raise
    except Exception as exc:
        _write(stream, f"[FAIL] Model readiness check failed: {exc}\n")
        raise BootError(f"Model readiness probe failed: {exc}") from exc
    total_ms = (time.monotonic() - started) * 1000.0
    report.probe_ms = probe_ms if probe_ms else total_ms
    report.probe_chars = int(chars or 0)
    report.stages.append(BootStage(label="Model ready", duration_ms=total_ms, ok=True))
    _write(stream, "[ OK ] Model ready\n")
    _write(stream, "\nA.S.I.S. ready.\n")
    return report
