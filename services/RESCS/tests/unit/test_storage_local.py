"""Local filesystem object store tests."""

from __future__ import annotations

import pytest

from rescs.errors import StorageError
from rescs.storage.local import LocalObjectStore


def test_creates_base_dir(tmp_path):
    LocalObjectStore(tmp_path / "nested" / "store")
    assert (tmp_path / "nested" / "store").is_dir()


def test_round_trip(tmp_path):
    store = LocalObjectStore(tmp_path / "store")
    store.put("rec-123", b"payload-data")
    assert store.exists("rec-123")
    assert store.get("rec-123") == b"payload-data"
    assert (tmp_path / "store" / "rec-123").is_file()


def test_missing_get_raises(tmp_path):
    store = LocalObjectStore(tmp_path / "store")
    with pytest.raises(StorageError):
        store.get("nope")


def test_delete_removes_blob(tmp_path):
    store = LocalObjectStore(tmp_path / "store")
    store.put("abc", b"data")
    store.delete("abc")
    assert not store.exists("abc")
    store.delete("abc")


def test_path_traversal_rejected(tmp_path):
    store = LocalObjectStore(tmp_path / "store")
    with pytest.raises(StorageError):
        store.put("../escape", b"x")
    with pytest.raises(StorageError):
        store.get("../escape")


def test_path_traversal_vectors_never_escape_base(tmp_path):
    store = LocalObjectStore(tmp_path / "store")
    vectors = [
        "../escape",
        "../../escape",
        "..\\escape",
        "/absolute/path",
        "/etc/passwd",
        "sub/dir",
        "",
        "x" * 129,
    ]
    for vector in vectors:
        with pytest.raises(StorageError):
            store.put(vector, b"x")
        with pytest.raises(StorageError):
            store.get(vector)
    # Nothing escaped: the base dir holds no traversal artifacts and the
    # parent directory gained no new entries from the rejected writes.
    assert [p.name for p in (tmp_path / "store").iterdir() if not p.name.startswith(".")] == []
    assert sorted(p.name for p in tmp_path.iterdir()) == ["store"]


def test_persists_across_instances(tmp_path):
    base = tmp_path / "store"
    first = LocalObjectStore(base)
    first.put("persist-me", b"bytes")
    second = LocalObjectStore(base)
    assert second.get("persist-me") == b"bytes"


def test_put_stream_failure_leaves_no_tmp(tmp_path):
    base = tmp_path / "store"
    store = LocalObjectStore(base)

    def _failing():
        yield b"partial"
        raise RuntimeError("chunk source exploded")

    with pytest.raises(RuntimeError, match="chunk source exploded"):
        store.put_stream("obj-1", _failing())
    leftovers = [p for p in base.iterdir() if p.suffix == ".tmp" or ".tmp" in p.name]
    assert leftovers == []
    assert not store.exists("obj-1")


def test_get_stream_abandon_releases_file(tmp_path):
    import os

    base = tmp_path / "store"
    store = LocalObjectStore(base)
    store.put("obj-1", b"0123456789")
    stream = store.get_stream("obj-1", chunk_size=2)
    assert next(stream) == b"01"
    stream.close()
    # On Windows an open handle blocks deletion: this proves the close.
    os.remove(base / "obj-1")
    assert not (base / "obj-1").exists()
