"""Tests for the memory subsystem: storage, recall, search and clearing."""

from __future__ import annotations

import pytest

from asis.memory import MemoryCategory


def test_remember_returns_persisted_memory(memory_manager):
    memory = memory_manager.remember(
        "User's name is Rishik.",
        category=MemoryCategory.USER,
        importance=10,
    )

    assert memory.memory_id is not None
    assert memory.content == "User's name is Rishik."
    assert memory.category is MemoryCategory.USER
    assert memory.importance == 10


def test_recall_after_remember(memory_manager):
    saved = memory_manager.remember("User plays chess.")

    recalled = memory_manager.recall(saved.memory_id)

    assert recalled is not None
    assert recalled.content == "User plays chess."


def test_recall_unknown_id_returns_none(memory_manager):
    assert memory_manager.recall(9999) is None


def test_forget_removes_memory(memory_manager):
    saved = memory_manager.remember("User likes coffee.")

    assert memory_manager.forget(saved.memory_id) is True
    assert memory_manager.recall(saved.memory_id) is None


def test_all_memories_filters_by_category(memory_manager):
    memory_manager.remember("User is building A.S.I.S.", category=MemoryCategory.USER)
    memory_manager.remember("I am the AI assistant.", category=MemoryCategory.ASSISTANT)

    user_results = memory_manager.all_memories(category=MemoryCategory.USER)
    assistant_results = memory_manager.all_memories(category=MemoryCategory.ASSISTANT)

    assert len(user_results) == 1
    assert len(assistant_results) == 1
    assert user_results[0].content.startswith("User is building")


def test_search_matches_substring(memory_manager):
    memory_manager.remember("User is building R.I.S.A.R.M.S.")
    memory_manager.remember("User likes coffee.")

    results = memory_manager.search("R.I.S.A.R.M.S.")

    assert len(results) == 1
    assert "R.I.S.A.R.M.S." in results[0].content


def test_empty_search_returns_nothing(memory_manager):
    memory_manager.remember("User plays chess.")
    assert memory_manager.search("") == []


def test_clear_removes_all(memory_manager):
    memory_manager.remember("User reads books.")
    memory_manager.remember("User plays guitar.")

    assert memory_manager.clear() == 2
    assert memory_manager.all_memories() == []


def test_importance_is_bounded(memory_manager):
    with pytest.raises(ValueError):
        memory_manager.remember("allowed?", importance=99)
    with pytest.raises(ValueError):
        memory_manager.remember("allowed?", importance=0)


def test_memory_rejects_blank_content(memory_manager):
    with pytest.raises(ValueError):
        memory_manager.remember("   ")


def test_legacy_full_dump_warns_but_still_works(memory_manager):
    import warnings

    memory_manager.remember("User likes tea.")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        blob = memory_manager.build_memory_context()
    assert "User likes tea." in blob
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)


def test_memory_search_wrapper_warns(memory_manager):
    import warnings

    from asis.memory import MemorySearch

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        searcher = MemorySearch(memory_manager.storage)
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)
    assert searcher.storage is memory_manager.storage
