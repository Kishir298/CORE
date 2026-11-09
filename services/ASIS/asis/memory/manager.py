"""
High-level memory manager for A.S.I.S.

Provides CRUD plus the formatted memory context used by the prompt
assembler. Cloud persistence is not performed here; that is R.E.S.C.S.'
responsibility once wired.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from asis.events.bus import EventBus
from asis.events.events import Event, EventType
from asis.logging.logger import get_logger

from .models import Memory, MemoryCategory, MemoryType
from .storage import MemoryStorage

_MEMORY_RULES = (
    "MEMORY RULES:\n"
    "- User memories describe the user.\n"
    "- Identity memories describe A.S.I.S.\n"
    "- Use these memories when relevant.\n"
    "- If the user asks what they shared earlier, answer from the memories\n"
    "  shown, even when this conversation just started.\n"
    "- Never invent memories.\n"
    "- Never claim to remember something that is not shown.\n"
    "- Never deny a memory that is shown.\n"
    "- Do not mention the memory system unless asked."
)

_STOPWORDS = frozenset(
    {
        "what",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "whose",
        "why",
        "how",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "do",
        "does",
        "did",
        "done",
        "have",
        "has",
        "had",
        "having",
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "if",
        "then",
        "else",
        "for",
        "of",
        "at",
        "by",
        "to",
        "in",
        "on",
        "with",
        "about",
        "into",
        "you",
        "your",
        "yours",
        "me",
        "my",
        "mine",
        "we",
        "our",
        "ours",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "there",
        "here",
        "please",
        "tell",
        "know",
        "remember",
        "recall",
        "something",
        "anything",
    }
)


def _query_keywords(query: str) -> list[str]:
    """Extract significant search tokens from a natural-language query."""
    import re

    tokens = re.findall(r"[A-Za-z0-9']+", query.lower())
    keywords: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        cleaned = token.strip("'")
        if len(cleaned) < 3 or cleaned in _STOPWORDS or cleaned in seen:
            continue
        seen.add(cleaned)
        keywords.append(cleaned)
    # Fall back to the raw stripped query when everything was filtered,
    # so very short inputs (e.g. a name) still search.
    if not keywords:
        fallback = query.strip()
        if fallback:
            keywords.append(fallback[:64])
    return keywords


def _is_generic_recall(text: str) -> bool:
    """Return True for keyword-free recall phrasing needing fallback."""
    import re as _re

    return bool(
        _re.search(
            r"\b(what did i (just )?(tell|say)|what do you (remember|recall|know)"
            r"|do you remember|what have i (told|said))\b",
            text.lower(),
        )
    )


class MemoryManager:
    """High-level interface for A.S.I.S. persistent memory."""

    def __init__(
        self,
        storage: MemoryStorage,
        event_bus: EventBus | None = None,
    ) -> None:
        self.storage = storage
        self.event_bus = event_bus
        self.logger = get_logger("memory")

    def _publish(
        self,
        event_type: EventType,
        **data,
    ) -> None:
        if self.event_bus is None:
            return

        self.event_bus.publish(
            Event(
                type=event_type,
                data=data,
                source="memory",
            )
        )

    def remember(
        self,
        content: str,
        category: MemoryCategory = MemoryCategory.GENERAL,
        memory_type: MemoryType = MemoryType.FACT,
        importance: int = 5,
        metadata: dict[str, Any] | None = None,
    ) -> Memory:
        """Create and persist a new memory."""
        memory = Memory(
            content=content,
            category=category,
            memory_type=memory_type,
            importance=importance,
            metadata=metadata or {},
        )

        saved = self.storage.save(memory)

        self.logger.info("Memory saved: %s", saved.memory_id)
        self._publish(EventType.MEMORY_SAVED, memory_id=saved.memory_id)

        return saved

    def recall(self, memory_id: int) -> Memory | None:
        """Retrieve one memory."""
        return self.storage.get(memory_id)

    def update(self, memory: Memory) -> Memory | None:
        """Update an existing memory."""
        return self.storage.update(memory)

    def forget(self, memory_id: int) -> bool:
        """Delete one memory."""
        deleted = self.storage.delete(memory_id)

        if deleted:
            self.logger.info("Memory deleted: %s", memory_id)
            self._publish(EventType.MEMORY_DELETED, memory_id=memory_id)

        return deleted

    def clear(self) -> int:
        """Delete every stored memory."""
        count = self.storage.clear()

        if count:
            self.logger.info("Memory cleared: %d items", count)
            self._publish(EventType.MEMORY_CLEARED, count=count)

        return count

    def search(
        self,
        query: str,
        category: MemoryCategory | None = None,
    ) -> list[Memory]:
        """Search stored memories."""
        return self.storage.search(query, category=category)

    def all_memories(
        self,
        category: MemoryCategory | None = None,
    ) -> list[Memory]:
        """Return every stored memory."""
        return self.storage.list_all(category=category)

    def with_importance(self, memory: Memory, importance: int) -> Memory:
        """Return a copy of a memory with a new importance."""
        return replace(memory, importance=importance)

    def build_memory_context(self) -> str:
        """Build the long-term memory section for the system prompt.

        DEPRECATED legacy full-dump path kept for backwards compatibility.
        Prefer :meth:`search_context` for query-scoped retrieval during
        inference: dumping every stored memory into every request breaks
        relevance ranking, limits, and token bounds. Emits a
        DeprecationWarning on use.
        """
        import warnings

        warnings.warn(
            "build_memory_context is deprecated; use search_context instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        by_category = {
            category: self.storage.list_all(category=category)
            for category in MemoryCategory
        }

        lines: list[str] = ["LONG-TERM MEMORY:"]

        for category, memories in by_category.items():
            lines.extend(["", f"{category.value.upper()} MEMORIES:"])

            if memories:
                lines.extend(f"- {item.content}" for item in memories)
            else:
                lines.append("- None.")

        lines.extend(["", *_MEMORY_RULES.splitlines()])

        return "\n".join(lines)

    def search_context(self, query: str, limit: int = 5) -> str:
        """Build a query-scoped memory section for the system prompt.

        Retrieves only memories relevant to ``query`` via the existing
        storage text search. Keywords are extracted from the query so a
        natural question (``what is my name?``) still matches a stored
        fact (``User's name is ...``). Returns ``""`` when there is
        nothing relevant so inference proceeds normally. Stored memories
        are treated as data and are clearly separated from system
        instructions by the caller.
        """
        text = (query or "").strip()
        if not text:
            return ""

        keywords = _query_keywords(text)
        if not keywords:
            return ""

        seen: dict[int | None, Any] = {}
        ordered: list[Any] = []
        for keyword in keywords[:8]:
            try:
                matches = self.storage.search(keyword)
            except Exception:
                raise
            for item in matches:
                key = item.memory_id if item.memory_id is not None else id(item)
                if key not in seen:
                    seen[key] = True
                    ordered.append(item)

        if not ordered and _is_generic_recall(text):
            # Generic recall ("what did I just tell you?", "what do you
            # remember about me?") carries no content keywords. Fall back
            # to the most important recent memories so multi-turn recall
            # works; specific-but-unmatched queries still return "".
            try:
                recent = self.storage.list_all()
            except Exception:
                raise
            recent.sort(key=lambda m: (-m.importance, m.content))
            ordered = recent

        if not ordered:
            return ""

        ordered.sort(
            key=lambda m: (-m.importance, m.content),
        )
        scoped = ordered[: max(1, limit)]
        lines: list[str] = ["RELEVANT MEMORIES:"]
        lines.extend(f"- {item.content}" for item in scoped)
        return "\n".join(lines)
