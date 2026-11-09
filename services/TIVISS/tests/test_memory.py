import pytest

from tiviss.memory import LocalMemory, MemoryKeyError, MemoryRecord


@pytest.fixture
def memory():
    return LocalMemory()


def test_store_and_retrieve(memory):
    record = MemoryRecord(key="greeting", content="hello")
    stored = memory.store(record)
    retrieved = memory.retrieve(record.record_id)
    assert retrieved.key == "greeting"
    assert retrieved.content == "hello"
    assert retrieved.record_id == stored.record_id


def test_retrieve_missing_raises(memory):
    with pytest.raises(MemoryKeyError):
        memory.retrieve("nope")


def test_update(memory):
    record = memory.store(MemoryRecord(key="k", content="old"))
    assert memory.update(record.record_id, content="new") is True
    assert memory.retrieve(record.record_id).content == "new"
    assert memory.retrieve(record.record_id).record_id == record.record_id


def test_update_missing_returns_false(memory):
    assert memory.update("nope", content="x") is False


def test_delete(memory):
    record = memory.store(MemoryRecord(key="k", content="v"))
    assert memory.delete(record.record_id) is True
    with pytest.raises(MemoryKeyError):
        memory.retrieve(record.record_id)


def test_delete_missing_returns_false(memory):
    assert memory.delete("nope") is False


def test_search(memory):
    memory.store(MemoryRecord(key="alpha", content="hello world"))
    memory.store(MemoryRecord(key="beta", content="goodbye world"))
    memory.store(MemoryRecord(key="gamma", content="nothing"))

    result = memory.search("world")
    assert result.total == 2
    assert {r.key for r in result.records} == {"alpha", "beta"}

    result = memory.search("hello")
    assert result.total == 1
    assert result.records[0].key == "alpha"


def test_search_case_insensitive(memory):
    memory.store(MemoryRecord(key="k", content="Hello WORLD"))
    assert memory.search("hello").total == 1
    assert memory.search("WORLD").total == 1


def test_clear(memory):
    memory.store(MemoryRecord(key="a", content="1"))
    memory.store(MemoryRecord(key="b", content="2"))
    memory.clear()
    assert memory.metadata()["stored"] == 0
    assert len(memory) == 0


def test_metadata(memory):
    memory.store(MemoryRecord(key="a", content="1"))
    memory.store(MemoryRecord(key="b", content="2"))
    meta = memory.metadata()
    assert meta["backend"] == "local"
    assert meta["stored"] == 2
    assert meta["keys"] == ["a", "b"]


def test_record_with_content_preserves_identity():
    record = MemoryRecord(key="k", content="a")
    updated = record.with_content("b", metadata={"tag": "x"})
    assert updated.record_id == record.record_id
    assert updated.key == "k"
    assert updated.content == "b"
    assert updated.metadata == {"tag": "x"}
    assert updated.created_at == record.created_at
    assert updated.updated_at >= record.updated_at
