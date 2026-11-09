"""Tests for the application layer: memory extraction and storage."""

from __future__ import annotations

from asis.app import extract_memories, store_auto_memories
from asis.memory import MemoryCategory


def test_extract_name():
    memories = extract_memories("My name is Rishik and I love coding.")

    assert any(
        category is MemoryCategory.USER and "Rishik" in content
        for content, category, _importance in memories
    )


def test_extract_name_has_top_importance():
    memories = extract_memories("My name is Rishik.")
    content, category, importance = memories[0]

    assert importance == 10
    assert category is MemoryCategory.USER
    assert content == "User's name is Rishik."


def test_extract_like_as_loves():
    memories = extract_memories("I love playing guitar.")
    content, category, _importance = memories[0]

    assert "loves" in content
    assert "guitar" in content
    assert category is MemoryCategory.USER


def test_extract_identity_fact():
    memories = extract_memories("You are the AI.")

    assert any(
        category is MemoryCategory.ASSISTANT and "AI assistant" in content
        for content, category, _importance in memories
    )


def test_extract_ignores_irrelevant_text():
    assert extract_memories("What is the weather today?") == []


def test_store_auto_memories_persists():

    class DummyManager:
        def __init__(self):
            self.remembered: list[tuple] = []

        def remember(self, content, *, category, importance):
            self.remembered.append((content, category, importance))

    manager = DummyManager()
    count = store_auto_memories("I play chess.", manager)

    assert count == 1
    assert count == len(manager.remembered)
