"""In-memory repository behaviour tests."""

from __future__ import annotations

import uuid

import pytest

from rescs.domain import RecordData
from rescs.errors import ConflictError, NotFoundError


def make_record(**overrides) -> RecordData:
    values = dict(
        id=str(uuid.uuid4()),
        namespace="default",
        key=str(uuid.uuid4()),
        value={"n": 1},
    )
    values.update(overrides)
    return RecordData(**values)


def test_create_and_get(memory_record_repo):
    record = make_record()
    created = memory_record_repo.create(record)
    assert memory_record_repo.get(record.id) == created


def test_get_missing_raises(memory_record_repo):
    with pytest.raises(NotFoundError):
        memory_record_repo.get("missing-id")


def test_get_by_namespace_key(memory_record_repo):
    record = make_record(namespace="ns", key="k")
    memory_record_repo.create(record)
    found = memory_record_repo.get_by_namespace_key("ns", "k")
    assert found.id == record.id
    assert memory_record_repo.get_by_namespace_key("ns", "other") is None


def test_duplicate_id_conflict(memory_record_repo):
    record = make_record()
    memory_record_repo.create(record)
    with pytest.raises(ConflictError):
        memory_record_repo.create(record)


def test_duplicate_namespace_key_conflict(memory_record_repo):
    first = make_record(namespace="ns", key="same")
    second = make_record(namespace="ns", key="same")
    memory_record_repo.create(first)
    with pytest.raises(ConflictError):
        memory_record_repo.create(second)


def test_update_and_delete(memory_record_repo):
    record = make_record(value={"v": 1})
    memory_record_repo.create(record)
    record.value = {"v": 2}
    updated = memory_record_repo.update(record)
    assert updated.value == {"v": 2}
    memory_record_repo.delete(record.id)
    with pytest.raises(NotFoundError):
        memory_record_repo.get(record.id)


def test_update_missing_raises(memory_record_repo):
    with pytest.raises(NotFoundError):
        memory_record_repo.update(make_record())


def test_delete_missing_raises(memory_record_repo):
    with pytest.raises(NotFoundError):
        memory_record_repo.delete("missing")


def test_idempotency_lookup(memory_record_repo):
    record = make_record(idempotency_key="idem-1")
    memory_record_repo.create(record)
    assert memory_record_repo.find_by_idempotency_key("idem-1").id == record.id
    assert memory_record_repo.find_by_idempotency_key("nope") is None


def test_list_filters_and_pagination(memory_record_repo):
    namespace = "orders"
    for index in range(5):
        memory_record_repo.create(
            make_record(namespace=namespace, key=f"order-{index}", value={"i": index})
        )
    memory_record_repo.create(make_record(namespace="other", key="x"))

    page = memory_record_repo.list(namespace=namespace, limit=2, offset=1)
    assert page.total == 5
    assert len(page.items) == 2
    assert page.limit == 2
    assert page.offset == 1

    prefixed = memory_record_repo.list(namespace=namespace, key_prefix="order-3")
    assert prefixed.total == 1
    assert prefixed.items[0].key == "order-3"

    owned = memory_record_repo.list(owner="alice")
    assert owned.total == 0
