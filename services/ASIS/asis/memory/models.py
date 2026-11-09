"""
Data models for A.S.I.S. memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

MIN_IMPORTANCE = 1
MAX_IMPORTANCE = 10


class MemoryCategory(StrEnum):
    """Who a memory describes."""

    USER = "user"
    ASSISTANT = "assistant"
    GENERAL = "general"


class MemoryType(StrEnum):
    """What kind of information a memory holds."""

    FACT = "fact"
    PREFERENCE = "preference"
    CONTEXT = "context"
    SYSTEM = "system"


@dataclass(frozen=True)
class Memory:
    """A single persistent memory item (provenance extension, backward compat)."""

    content: str
    category: MemoryCategory = MemoryCategory.GENERAL
    memory_type: MemoryType = MemoryType.FACT
    importance: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    memory_id: int | None = None
    identity_id: str = "default"
    confidence: float = 0.7
    source: str = "user-stated"
    evidence: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("Memory content cannot be empty.")

        if not MIN_IMPORTANCE <= self.importance <= MAX_IMPORTANCE:
            raise ValueError(
                f"Memory importance must be between "
                f"{MIN_IMPORTANCE} and {MAX_IMPORTANCE}."
            )

        if not isinstance(self.category, MemoryCategory):
            raise TypeError(f"Invalid memory category: {self.category!r}.")

        if not isinstance(self.memory_type, MemoryType):
            raise TypeError(f"Invalid memory type: {self.memory_type!r}.")
