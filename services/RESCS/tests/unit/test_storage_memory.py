"""Memory object store tests."""

from __future__ import annotations

import pytest

from rescs.errors import StorageError
from rescs.storage.memory import MemoryObjectStore


def test_round_trip():
    store = MemoryObjectStore()
    store.put("obj-1", b"hello")
    assert store.exists("obj-1")
    assert store.get("obj-1") == b"hello"


def test_get_missing_raises():
    store = MemoryObjectStore()
    with pytest.raises(StorageError):
        store.get("missing")


def test_delete():
    store = MemoryObjectStore()
    store.put("obj-1", b"x")
    store.delete("obj-1")
    assert not store.exists("obj-1")
    store.delete("obj-1")


def test_overwrite():
    store = MemoryObjectStore()
    store.put("obj-1", b"a")
    store.put("obj-1", b"b")
    assert store.get("obj-1") == b"b"
