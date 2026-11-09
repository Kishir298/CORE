"""SQLAlchemy repository behaviour tests (sqlite in-memory)."""

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


def test_create_and_get(sqlalchemy_record_repo):
    record = make_record()
    sqlalchemy_record_repo.create(record)
    assert sqlalchemy_record_repo.get(record.id) == record


def test_get_missing_raises(sqlalchemy_record_repo):
    with pytest.raises(NotFoundError):
        sqlalchemy_record_repo.get("missing")


def test_get_by_namespace_key(sqlalchemy_record_repo):
    record = make_record(namespace="ns", key="k")
    sqlalchemy_record_repo.create(record)
    found = sqlalchemy_record_repo.get_by_namespace_key("ns", "k")
    assert found.id == record.id


def test_duplicate_namespace_key_conflict(sqlalchemy_record_repo):
    first = make_record(namespace="ns", key="same")
    second = make_record(namespace="ns", key="same")
    sqlalchemy_record_repo.create(first)
    with pytest.raises(ConflictError):
        sqlalchemy_record_repo.create(second)


def test_duplicate_idempotency_conflict(sqlalchemy_record_repo):
    first = make_record(idempotency_key="idem-x")
    second = make_record(idempotency_key="idem-x")
    sqlalchemy_record_repo.create(first)
    with pytest.raises(ConflictError):
        sqlalchemy_record_repo.create(second)


def test_update_persists(sqlalchemy_record_repo):
    record = make_record(value={"v": 1})
    sqlalchemy_record_repo.create(record)
    record.value = {"v": 3}
    record.version = 2
    updated = sqlalchemy_record_repo.update(record)
    fetched = sqlalchemy_record_repo.get(record.id)
    assert updated.value == {"v": 3}
    assert fetched.version == 2


def test_delete(sqlalchemy_record_repo):
    record = make_record()
    sqlalchemy_record_repo.create(record)
    sqlalchemy_record_repo.delete(record.id)
    with pytest.raises(NotFoundError):
        sqlalchemy_record_repo.get(record.id)
    with pytest.raises(NotFoundError):
        sqlalchemy_record_repo.delete(record.id)


def test_idempotency_lookup(sqlalchemy_record_repo):
    record = make_record(idempotency_key="idem-y")
    sqlalchemy_record_repo.create(record)
    assert sqlalchemy_record_repo.find_by_idempotency_key("idem-y").id == record.id


def test_list_filters_and_pagination(sqlalchemy_record_repo):
    ns = "events"
    for index in range(4):
        sqlalchemy_record_repo.create(
            make_record(namespace=ns, key=f"event-{index}", value={"i": index})
        )
    page = sqlalchemy_record_repo.list(namespace=ns, limit=2, offset=1)
    assert page.total == 4
    assert len(page.items) == 2

    prefixed = sqlalchemy_record_repo.list(namespace=ns, key_prefix="event-0")
    assert prefixed.total == 1
    assert prefixed.items[0].key == "event-0"


def test_search_treats_percent_underscore_as_literals(sqlalchemy_record_repo):
    sqlalchemy_record_repo.create(make_record(key="100%-off_sale"))
    sqlalchemy_record_repo.create(make_record(key="100X-offYsale"))
    page = sqlalchemy_record_repo.search("100%-off_sale")
    keys = {item.key for item in page.items}
    assert "100%-off_sale" in keys
    assert "100X-offYsale" not in keys

def test_search_wildcard_query_matches_exact_total(sqlalchemy_record_repo):
    sqlalchemy_record_repo.create(make_record(key="100%-off_sale"))
    sqlalchemy_record_repo.create(make_record(key="100X-offYsale"))
    page = sqlalchemy_record_repo.search("100%-off_sale")
    assert page.total == 1
    assert [item.key for item in page.items] == ["100%-off_sale"]

