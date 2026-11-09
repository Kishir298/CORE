"""
Prompt context assembly for A.S.I.S.

Assembles the system prompt from stable identity/personality plus dynamic
mode/memory/capabilities sections with correctness rules, then builds the
final message list with history trimmed to the configured limit.

Stable (identity/personality/rules) vs dynamic (mode/memory/capabilities)
split keeps prompts bounded: total system text never exceeds
``context_char_limit``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from asis.configuration.settings import settings
from asis.identity.identity import Identity

from .models import AIMessage, MessageRole

MemoryContextProvider = Callable[[], str]

_MEMORY_RULES = (
    "MEMORY RULES:\n"
    "- Use these memories when relevant.\n"
    "- If the user asks what they shared earlier, answer from the memories\n"
    "  shown, even when this conversation just started.\n"
    "- Never invent memories.\n"
    "- Never claim to remember something that is not shown.\n"
    "- Never deny a memory that is shown.\n"
    "- Do not mention the memory system unless asked."
)

try:
    from asis.identity.personality import BEHAVIOR_PRINCIPLES as _BEHAVIOR_TEXT
except Exception:
    _BEHAVIOR_TEXT = ""

try:
    from asis.identity.personality import SAFETY_BOUNDS as _SAFETY_TEXT
except Exception:
    _SAFETY_TEXT = ""

_BEHAVIOR_RULES = (_BEHAVIOR_TEXT or "").strip()
# Immutable safety tail: DEFAULT_PERSONALITY already carries equivalent
# safety prose, but a custom ASIS_PERSONALITY_FILE could strip it. This
# compact bound always reaches the model regardless of personality
# overrides, so safety never depends on user-supplied template text.
_SAFETY_RULES = (_SAFETY_TEXT or "").strip()


class ContextAssembler:
    """Builds the context sent alongside user history."""

    def __init__(
        self,
        identity: Identity,
        memory_context_provider: MemoryContextProvider | None = None,
        mode_context_provider: MemoryContextProvider | None = None,
        capabilities_provider: MemoryContextProvider | None = None,
        constraints_provider: MemoryContextProvider | None = None,
        max_context_messages: int | None = None,
        context_char_limit: int | None = None,
    ) -> None:
        self.identity = identity
        self.memory_context_provider = memory_context_provider
        self.mode_context_provider = mode_context_provider
        self.capabilities_provider = capabilities_provider
        self.constraints_provider = constraints_provider
        # Per-turn flag (set by AssistantApp from the orchestrator plan):
        # memory-recall turns lead with memory right after SYSTEM so the
        # model grounds in shown facts even with an empty conversation.
        self.memory_first = False
        self.max_context_messages = (
            max_context_messages or settings.ai.max_context_messages
        )
        self.context_char_limit = context_char_limit or settings.ai.context_char_limit

    def _section(self, provider: MemoryContextProvider | None) -> str:
        if provider is None:
            return ""
        try:
            text = provider() or ""
        except Exception:
            return ""
        return text.strip()

    def estimate_size(self) -> int:
        """Return the current system-prompt length (stable + dynamic)."""
        return len(self.system_prompt())

    def system_prompt(self) -> str:
        """Build the full labeled, bounded system prompt."""
        stable = f"SYSTEM:\n{self.identity.system_prompt().strip()}"
        sections = [stable]

        memory_text = self._section(self.memory_context_provider)
        if memory_text and self.memory_first:
            sections.append(memory_text)

        mode_text = self._section(self.mode_context_provider)
        if mode_text:
            sections.append(f"MODE:\n{mode_text}")

        caps = self._section(self.capabilities_provider)
        if caps:
            if caps.lstrip().startswith("CAPABILITIES:"):
                sections.append(caps)
            else:
                sections.append(f"CAPABILITIES:\n{caps}")

        if memory_text and not self.memory_first:
            sections.append(memory_text)

        constraints = self._section(self.constraints_provider)
        if constraints:
            if constraints.lstrip().startswith("CONSTRAINTS:"):
                sections.append(constraints)
            else:
                sections.append(f"CONSTRAINTS:\n{constraints}")

        sections.append(_MEMORY_RULES)
        if _BEHAVIOR_RULES:
            sections.append(_BEHAVIOR_RULES)
        if _SAFETY_RULES:
            sections.append(_SAFETY_RULES)

        prompt = "\n\n".join(s for s in sections if s.strip())
        if len(prompt) > self.context_char_limit:
            # Prefer keeping the stable identity head intact; always respect
            # the hard bound (tests use tiny limits smaller than stable).
            budget = self.context_char_limit
            marker = "\n\n[context truncated]"
            if len(stable) + len(marker) >= budget:
                prompt = prompt[:budget].rstrip() + marker
            else:
                tail_budget = max(0, budget - len(stable) - len(marker))
                truncated_tail = "\n\n".join(
                    s for s in sections[1:] if s.strip()
                )[:tail_budget].rstrip()
                prompt = stable + ("\n\n" + truncated_tail if truncated_tail else "")
                prompt = prompt.rstrip() + marker
        return prompt

    def build_messages(
        self,
        history: Sequence[AIMessage],
    ) -> list[AIMessage]:
        """Build the final message list for the AI model."""
        limit = max(1, self.max_context_messages)
        recent = list(history)[-limit:]

        return [
            AIMessage(
                role=MessageRole.SYSTEM,
                content=self.system_prompt(),
            ),
            *recent,
        ]
