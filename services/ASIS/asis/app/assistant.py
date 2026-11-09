"""
Stateful A.S.I.S. application runtime with GENERAL/CODING modes.

Owns one conversation session for its lifetime and wires together the
already-built subsystems:

    user input -> ConversationSession -> memory retrieval ->
    ContextAssembler -> InferenceEngine -> AIManager -> action decision ->
    ToolRouter/Permission/Executor -> final response -> ConversationSession

Mode changes behavior, not the model runtime: GENERAL is the normal
assistant, CODING is A.S.C.S. (same provider/model instance, mode
instructions + repository context + coding tools). Shared by the text
CLI and the voice loop. Memory failures are fail-open (log +
continue); inference failures preserve conversation state.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from asis.ai.context import ContextAssembler
from asis.ai.conversation import ConversationSession
from asis.ai.inference import InferenceEngine
from asis.ai.manager import AIManager
from asis.ai.orchestrator import Intent, build_plan
from asis.configuration.settings import settings
from asis.events.bus import EventBus
from asis.identity.identity import Identity
from asis.logging.logger import get_logger
from asis.system.interrupt import InterruptCoordinator
from asis.tools.result import ToolResult
from asis.tools.router import ToolRouter

from .actions import ToolRequest, format_tool_result_for_context, parse_tool_request
from .memories import store_auto_memories
from .modes import AssistantMode, parse_mode
from .native_tools import (
    max_tool_calls,
    native_tools_enabled,
    normalize_native_calls,
)
from .prompt import (
    build_capabilities_section,
    build_constraints_section,
    build_memory_section,
    build_mode_section,
)
from .routers import (
    build_coding_tool_router,
    build_default_tool_router,
    ensure_all_tools,
)

# Intents that never need the native function-calling attempt: a single
# plain generation is faster (no tool-definition prompt tax) and
# sufficient. Only true small-talk skips; QUESTION/MEMORY_QUERY/VOICE and
# TOOL_REQUEST/CALCULATION/CODING always keep the native-first path so
# natural questions ("what is 6 times 7", "core status?") can still use
# tools. All other intents keep the native-first path with the
# heuristic fallback unchanged.
_NATIVE_SKIP_INTENTS = frozenset(
    {
        Intent.GENERAL_CHAT,
    }
)


class AssistantApp:
    """Stateful chat application owning conversation, memory, mode and tools."""

    def __init__(
        self,
        identity: Identity,
        ai: AIManager,
        memory,
        tools_router: ToolRouter | None = None,
        interrupts: InterruptCoordinator | None = None,
        event_bus: EventBus | None = None,
        max_memory_items: int = 5,
        mode: AssistantMode | str | None = None,
        workspace=None,
        core=None,
    ) -> None:
        self.identity = identity
        self.ai = ai
        self.memory = memory
        self.event_bus = event_bus
        self.interrupts = interrupts
        self.logger = get_logger("app.assistant")
        self.session = ConversationSession()
        self._pending_memory_query = ""
        self._max_memory_items = max(1, max_memory_items)
        self._last_plan = None
        self._mode = self._coerce_mode(mode)
        self._workspace = workspace
        self._coding_resolver = None
        self._coding_router: ToolRouter | None = None
        self.core = core
        self.assembler = ContextAssembler(
            identity=identity,
            memory_context_provider=self._assembler_context,
            mode_context_provider=self._mode_section,
            capabilities_provider=self._capabilities_section,
            constraints_provider=self._constraints_section,
            max_context_messages=settings.ai.max_context_messages,
            context_char_limit=settings.ai.context_char_limit,
        )
        self.engine = InferenceEngine(
            manager=ai, assembler=self.assembler, interrupts=interrupts
        )
        self._general_router = tools_router or build_default_tool_router()
        if self.event_bus is not None:
            with contextlib.suppress(Exception):
                executor = getattr(self._general_router, "executor", None)
                if executor is not None:
                    executor.event_bus = self.event_bus
        ensure_all_tools(self._general_router, self.core)
        translation_settings = settings.translation
        self._translation_source = translation_settings.default_source
        self._translation_target = translation_settings.default_target

    @property
    def core_available(self) -> bool:
        """Return whether the optional CORE session is currently usable."""
        if self.core is None:
            return False
        try:
            return bool(self.core.is_available())
        except Exception:
            return False

    def core_status_text(self) -> str:
        """Short human-readable CORE status line (no secrets)."""
        if self.core is None:
            return "CORE: disabled."
        try:
            status = self.core.status()
        except Exception as exc:
            return f"CORE: unknown ({exc})"
        state = getattr(status.state, "value", str(status.state))
        return f"CORE: {state.lower()} (connected={status.connected})."

    @staticmethod
    def _coerce_mode(mode: AssistantMode | str | None) -> AssistantMode:
        if mode is None:
            return parse_mode(settings.coding.default_mode)
        if isinstance(mode, AssistantMode):
            return mode
        return parse_mode(mode)

    @property
    def mode(self) -> AssistantMode:
        """Return the active assistant mode."""
        return self._mode

    def set_mode(self, mode: AssistantMode | str) -> AssistantMode:
        """Switch mode without touching the provider/model instance."""
        self._mode = self._coerce_mode(mode)
        self.logger.info("Assistant mode: %s", self._mode.value)
        return self._mode

    @property
    def translation_source(self) -> str:
        """Session source language (``auto`` means detect per message)."""
        return self._translation_source

    @property
    def translation_target(self) -> str:
        """Session target language."""
        return self._translation_target

    def set_translation_languages(
        self, source: str | None = None, target: str | None = None
    ) -> tuple[str, str]:
        """Set session translation languages (validated registry codes)."""
        from asis.translation.languages import normalize_code

        if source is not None:
            cleaned = source.strip().lower()
            if cleaned != "auto" and normalize_code(cleaned) is None:
                raise ValueError(f"Unsupported source language: {source!r}.")
            self._translation_source = cleaned
        if target is not None:
            code = normalize_code(target)
            if code is None:
                raise ValueError(f"Unsupported target language: {target!r}.")
            self._translation_target = code
        return self._translation_source, self._translation_target

    @property
    def workspace(self):
        """Return the coding workspace, resolving lazily on first use."""
        if self._workspace is None:
            from asis.coding.workspace import resolve_workspace

            self._workspace = resolve_workspace()
        elif isinstance(self._workspace, (str, Path)):
            from asis.coding.workspace import resolve_workspace

            self._workspace = resolve_workspace(self._workspace)
        return self._workspace

    def _memory_context(self) -> str:
        return build_memory_section(
            self._pending_memory_query,
            self.memory,
            self._max_memory_items,
            self.logger,
        )

    def _mode_section(self) -> str:
        """Mode instructions for the labeled MODE context block."""
        return build_mode_section(self._mode)

    def _capabilities_section(self) -> str:
        """Bounded capabilities summary + active tool names (no schemas)."""
        try:
            names = sorted(self.tools_router.registry.list_names())
        except Exception:
            names = []
        return build_capabilities_section(names)

    def _constraints_section(self) -> str:
        """Per-turn orchestrator constraints (empty outside a planned turn)."""
        return build_constraints_section(self._last_plan)

    def _assembler_context(self) -> str:
        sections = []
        memory_text = self._memory_context()
        if memory_text:
            sections.append(memory_text)
        if self._mode is AssistantMode.CODING:
            try:
                if self._coding_resolver is None:
                    from asis.coding.context import CodingContextResolver

                    self._coding_resolver = CodingContextResolver(self.workspace)
                sections.append(self._coding_resolver.build())
            except Exception as exc:
                self.logger.warning("Coding context unavailable, continuing: %s", exc)
        text = "\n\n".join(s for s in sections if s.strip())
        return text

    @property
    def tools_router(self) -> ToolRouter:
        """Return the router for the active mode (shared executor policy)."""
        if self._mode is AssistantMode.CODING:
            if self._coding_router is None:
                executor = getattr(self._general_router, "executor", None)
                self._coding_router = build_coding_tool_router(
                    self.workspace, executor=executor
                )
                ensure_all_tools(self._coding_router, self.core)
            return self._coding_router
        return self._general_router

    @tools_router.setter
    def tools_router(self, router: ToolRouter | None) -> None:
        if router is not None:
            self._general_router = router
            ensure_all_tools(router, self.core)

    def _execute_tool(self, request: ToolRequest) -> ToolResult:
        try:
            return self.tools_router.execute(request.tool_name, **request.arguments)
        except Exception as exc:
            self.logger.exception("Tool dispatch failed: %s", request.tool_name)
            return ToolResult.failure(error=str(exc), tool_name=request.tool_name)

    def _generate_text(self, messages, on_chunk=None) -> str:
        """Generate user-visible text, streamed when a callback is given."""
        if on_chunk is None:
            return self.engine.generate(messages).content
        try:
            return self.engine.generate_streamed(messages, on_chunk=on_chunk)
        except Exception as exc:
            from asis.errors import CancellationError

            if isinstance(exc, CancellationError):
                raise
            self.logger.warning("Streamed generation failed; using fallback.")
            return self.engine.generate(messages).content

    def _finalize_with_text(self, text: str) -> str:
        self.session.add_assistant(text)
        return text

    def _native_tool_definitions(self, tool_hint: str | None):
        """Gate + build the tool definitions for a native turn.

        Returns None when native calling is unavailable (caller falls back
        to heuristics).
        """
        if not native_tools_enabled():
            return None
        provider = getattr(self.ai, "provider", None)
        if provider is None or not getattr(
            provider, "supports_native_tools", False
        ):
            return None
        from asis.ai.tool_schemas import select_tool_definitions, tool_definitions_for

        try:
            definitions = tool_definitions_for(self.tools_router.registry)
        except Exception:
            self.logger.warning(
                "Tool schema generation failed; using heuristic fallback."
            )
            return None
        # Intent-aware narrowing: expose only relevant tools to the model
        # (e.g. calculator turns send just `calculate`). Unknown hints and
        # hints matching nothing keep the full set so the model is never
        # starved; permissions are still enforced at execution.
        definitions = select_tool_definitions(definitions, tool_hint)
        if not definitions:
            return None
        return definitions

    def _filter_allowed_calls(self, requests, errors, allowed):
        """Drop calls outside the model-visible definition set."""
        if len(allowed) < len(list(self.tools_router.registry.list_names())):
            from .native_tools import NativeToolError

            kept: list = []
            for request in requests:
                if request.tool_name in allowed:
                    kept.append(request)
                else:
                    errors.append(
                        NativeToolError(
                            kind="unknown_tool",
                            message=(
                                "Unknown tool: "
                                f"{request.tool_name!r}."
                            ),
                            call_name=request.tool_name,
                        )
                    )
            return kept
        return requests

    def _finalize_native_turn(self, on_chunk=None) -> str:
        """End a native turn with a plain final generation."""
        try:
            if on_chunk is None:
                final = self.engine.generate(self.session.messages)
                text = final.content
            else:
                text = self._generate_text(self.session.messages, on_chunk=on_chunk)
        finally:
            self._pending_memory_query = ""
        self.session.add_assistant(text)
        return text

    def _run_native_tool_loop(
        self, user_text: str, on_chunk=None, tool_hint: str | None = None
    ) -> str | None:
        """Bounded native function-calling turn; None → heuristic fallback.

        The model receives tool definitions derived from the active-mode
        registry and may request structured calls. Every call is
        normalized to a ToolRequest and executed through the SAME
        ToolRouter/permission path as heuristic intents. At most
        ``max_calls_per_turn`` validated calls run; the turn always ends
        with a plain final generation. Any native failure (unsupported
        provider, transport error, no usable calls) returns None so the
        caller falls back to the heuristic path.
        """
        definitions = self._native_tool_definitions(tool_hint)
        if not definitions:
            return None
        limit = max_tool_calls()
        try:
            response = self.engine.generate_with_tools(
                self.session.messages, definitions
            )
        except Exception:
            self.logger.warning("Native tool request failed; using fallback.")
            return None
        self._pending_memory_query = ""
        if not response.tool_calls:
            # Model answered directly; record and return (fallback not
            # needed, but heuristics must not double-fire on this text).
            if (response.content or "").strip():
                self.session.add_assistant(response.content)
                return response.content
            return None
        calls_made = 0
        allowed = {item.name for item in definitions}
        while response.tool_calls and calls_made < limit:
            requests, errors = normalize_native_calls(
                response.tool_calls, self.tools_router.registry
            )
            # Enforce the filtered set: the model only saw `definitions`,
            # so calls outside it are rejected before permission/execution.
            requests = self._filter_allowed_calls(requests, errors, allowed)
            if (response.content or "").strip():
                self.session.add_assistant(response.content)
            for error in errors:
                self.session.add_assistant(
                    f"[tool {error.call_name or 'unknown'} error] {error.message}"
                )
            if not requests:
                break
            for request in requests:
                if calls_made >= limit:
                    break
                result = self._execute_tool(request)
                self.session.add_assistant(format_tool_result_for_context(result))
                calls_made += 1
            if calls_made >= limit:
                break
            try:
                response = self.engine.generate_with_tools(
                    self.session.messages, definitions
                )
            except Exception:
                self.logger.warning("Native continuation failed; finalizing.")
                break
            if not response.tool_calls and (response.content or "").strip():
                # The continuation already answers with the tool results
                # in context: it is the final response.
                self.session.add_assistant(response.content)
                return response.content
        # Fell out of the loop (call bound reached, calls rejected, or
        # continuation failed/empty): finalize with a plain generation.
        return self._finalize_native_turn(on_chunk)

    def _run_translation_turn(self, text: str) -> str:
        """Translate directly through the shared router (no LLM needed)."""
        result = self.tools_router.execute(
            "translate_text",
            text=text,
            target_language=self._translation_target,
            source_language=self._translation_source,
        )
        if result.success:
            data = result.data or {}
            reply = str(data.get("translated_text", ""))
            if data.get("detected_source"):
                reply = f"[{data.get('source_language')}] {reply}"
            self.session.add_assistant(reply)
            return reply
        note = str(result.error or "translation failed.")
        self.session.add_assistant(f"[translation error] {note}")
        return note

    def _generate_plain_content(self, on_chunk=None):
        """Plain generation without tools (resets the pending memory query)."""
        try:
            if on_chunk is None:
                response = self.engine.generate(self.session.messages)
                return response.content
            return self._generate_text(self.session.messages, on_chunk=on_chunk)
        finally:
            self._pending_memory_query = ""

    def _generate_turn_content(self, plan, text: str, on_chunk=None):
        """Run native loop or plain generation; None only when skipped."""
        try:
            if plan.tool_hint == "none" or (
                plan.tool_hint is None and plan.intent in _NATIVE_SKIP_INTENTS
            ):
                # Explanation-only (or small-talk) turn: zero tool
                # definitions, straight to plain generation — same fast
                # path as GENERAL_CHAT, memory/context behavior unchanged.
                return (self._generate_plain_content(on_chunk), False)
            native_reply = self._run_native_tool_loop(
                text, on_chunk=on_chunk, tool_hint=plan.tool_hint
            )
            if native_reply is not None:
                return (native_reply, True)
            return (self._generate_plain_content(on_chunk), False)
        finally:
            self._pending_memory_query = ""

    def _finish_tool_turn(self, content: str, text: str, on_chunk=None) -> str:
        """Parse model output for tool calls; execute + finalize."""
        coding = self._mode is AssistantMode.CODING
        request = parse_tool_request(content, user_text=text, coding=coding)
        if request is None:
            self.session.add_assistant(content)
            return content

        result = self._execute_tool(request)
        # Record the intermediate model action + explicit tool result so the
        # history stays auditable; tool output is never user-authored.
        self.session.add_assistant(content)
        self.session.add_assistant(format_tool_result_for_context(result))

        self._pending_memory_query = ""
        try:
            if on_chunk is None:
                final = self.engine.generate(self.session.messages)
                final_text = final.content
            else:
                final_text = self._generate_text(
                    self.session.messages, on_chunk=on_chunk
                )
        finally:
            self._pending_memory_query = ""
        self.session.add_assistant(final_text)
        return final_text

    def chat(self, message: str) -> str:
        """Process one user message through the full wired pipeline."""
        return self.chat_streamed(message)

    def chat_streamed(self, message: str, on_chunk=None) -> str:
        """Process one message; stream user-visible chunks via ``on_chunk``.

        Orchestration (intent/memory/tool/mode) is deterministic and runs
        before inference. Tool/permission flow is unchanged; only the
        final user-visible generation streams when a callback is given.
        """
        text = (message or "").strip()
        if not text:
            return ""
        plan = build_plan(
            text,
            mode=self._mode.value,
            has_docs=True,
            memory_limit=self._max_memory_items,
        )
        self._last_plan = plan
        self.assembler.memory_first = plan.intent is Intent.MEMORY_QUERY
        store_auto_memories(text, self.memory)
        self.session.add_user(text)
        # Deterministic short-circuits (no model needed).
        if plan.intent is Intent.CORE_OPERATION:
            explicit = self._run_core_command(text)
            if explicit is not None:
                return explicit
            # Not actually a core command: fall through to normal handling.
        if self._mode is AssistantMode.TRANSLATION:
            return self._run_translation_turn(text)
        self._pending_memory_query = (
            plan.memory_query if plan.memory_needed else ""
        )
        content, from_native = self._generate_turn_content(plan, text, on_chunk=on_chunk)
        if from_native:
            return content
        return self._finish_tool_turn(content, text, on_chunk=on_chunk)

    def _run_core_command(self, text: str) -> str | None:
        """Execute an explicit ``core:`` user command; None when absent.

        Explicit commands bypass model inference deterministically and run
        through the same ToolRouter/permission path as model intents.
        """
        from .core_commands import parse_core_intent

        intent = parse_core_intent(text)
        if intent is None:
            return None
        if not self.core_available:
            note = "CORE_UNAVAILABLE: C.O.R.E. is not connected."
            self.session.add_assistant(note)
            return note
        try:
            result = self.tools_router.execute(intent.tool_name, **intent.kwargs)
        except Exception as exc:
            note = f"CORE tool failed: {exc}"
            self.session.add_assistant(note)
            return note
        if result.success:
            from asis.integrations.core.protocol import normalize_result

            summary = normalize_result(result.data)
            note = f"{intent.tool_name}: ok: {summary}"
        else:
            note = f"{intent.tool_name} failed: {result.error or 'unknown error'}"
        self.session.add_assistant(note)
        return note

    def history_roles(self) -> list[str]:
        """Return session roles (test helper)."""
        return [m.role.value for m in self.session.messages]

    @property
    def conversation(self) -> ConversationSession:
        """Expose the owned conversation session."""
        return self.session
