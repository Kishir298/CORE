"""
Automatic long-term memory extraction for A.S.I.S.

Explicit personal facts are detected from user text and persisted
without needing model inference. Patterns are conservative: only clear,
self-reported facts are stored.
"""

from __future__ import annotations

import re

from asis.memory.models import MemoryCategory

_NAME_PATTERN = re.compile(
    r"\bmy name is\s+([^,.!?]+)",
    flags=re.IGNORECASE,
)
_LIKE_PATTERN = re.compile(
    r"\bi (?:like|love)\s+(.+?)(?:(?:\.\s)|(?:!\s)|(?:\?\s)|$)",
    flags=re.IGNORECASE,
)
_LOVE_MATCH = re.compile(r"\bi love\b", flags=re.IGNORECASE)
_PLAY_PATTERN = re.compile(
    r"\bi play\s+(.+?)(?:(?:\.\s)|(?:!\s)|(?:\?\s)|$)",
    flags=re.IGNORECASE,
)
_READ_PATTERN = re.compile(
    r"\bi read\s+(.+?)(?:(?:\.\s)|(?:!\s)|(?:\?\s)|$)",
    flags=re.IGNORECASE,
)
_WORK_PATTERN = re.compile(
    r"\bi(?:'m| am)\s+(?:building|working on)\s+(.+?)(?:(?:\.\s)|(?:!\s)|(?:\?\s)|$)",
    flags=re.IGNORECASE,
)

_IDENTITY_PATTERNS: tuple[tuple[re.Pattern, str], ...] = (
    (
        re.compile(r"\byou(?:'re| are)\s+the ai\b", re.IGNORECASE),
        "I am the AI assistant being developed as A.S.I.S.",
    ),
    (re.compile(r"\byou(?:'re| are)\s+asis\b", re.IGNORECASE), "I am A.S.I.S."),
    (
        re.compile(r"\byou(?:'re| are)\s+the assistant\b", re.IGNORECASE),
        "I am the AI assistant in the R.I.S.A.R.M.S. project.",
    ),
    (
        re.compile(r"\bi(?:'m| am)\s+improving you\b", re.IGNORECASE),
        "The user is actively improving A.S.I.S.",
    ),
    (
        re.compile(r"\bi(?:'m| am)\s+building you\b", re.IGNORECASE),
        "The user is building A.S.I.S.",
    ),
)


def extract_memories(text: str) -> list[tuple[str, MemoryCategory, int]]:
    """Extract explicit personal facts into (content, category, importance)."""
    memories: list[tuple[str, MemoryCategory, int]] = []

    name = _NAME_PATTERN.search(text)
    if name and name.group(1).strip():
        memories.append(
            (f"User's name is {name.group(1).strip()}.", MemoryCategory.USER, 10)
        )

    like = _LIKE_PATTERN.search(text)
    if like and like.group(1).strip():
        verb = "loves" if _LOVE_MATCH.search(text) else "likes"
        memories.append(
            (f"User {verb} {like.group(1).strip()}.", MemoryCategory.USER, 8)
        )

    play = _PLAY_PATTERN.search(text)
    if play and play.group(1).strip():
        memories.append(
            (f"User plays {play.group(1).strip()}.", MemoryCategory.USER, 7)
        )

    read = _READ_PATTERN.search(text)
    if read and read.group(1).strip():
        memories.append(
            (f"User reads {read.group(1).strip()}.", MemoryCategory.USER, 7)
        )

    work = _WORK_PATTERN.search(text)
    if work and work.group(1).strip():
        memories.append(
            (f"User is working on {work.group(1).strip()}.", MemoryCategory.USER, 9)
        )

    for pattern, fact in _IDENTITY_PATTERNS:
        if pattern.search(text):
            memories.append((fact, MemoryCategory.ASSISTANT, 10))

    return memories


def store_auto_memories(text: str, memory_manager) -> int:
    """Persist extracted facts. Returns the number stored."""
    stored = 0

    for content, category, importance in extract_memories(text):
        memory_manager.remember(
            content,
            category=category,
            importance=importance,
        )
        stored += 1

    return stored
