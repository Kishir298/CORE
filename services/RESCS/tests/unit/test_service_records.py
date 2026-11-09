"""Record service behaviour tests against the in-memory repository."""

from __future__ import annotations

import pytest

from rescs.errors import ConflictError, InvalidRequestError, NotFoundError
from rescs.schemas.record import RecordCreate, RecordUpdate
from rescs.services.factory import build_services


@pytest.fixture()
def services():
    return build_services(use_memory=True)


def make_create(**overrides) -> RecordCreate:
    values = dict(
        namespace="default",
        key="key",
        value={"n": 1},
    )
    values.update(overrides)
    return RecordCreate(**values)


def make_update(**overrides) -> RecordUpdate:
    return RecordUpdate(**overrides)


def test_create_assigns_id_version_and_etag(services):
    record = services.records.create(make_create(key="a", value={"x": 1}))
    assert record.id
    assert record.version == 1
    assert record.etag
    assert record.created_at is not None
    assert record.updated_at is not None


def test_create_is_idempotent_by_key(services):
    payload = make_create(key="k", idempotency_key="idem-1")
    first = services.records.create(payload)
    second = services.records.create(payload)
    assert first.id == second.id
    assert second.version == 1


def test_create_conflict_on_duplicate_namespace_key(services):
    payload = make_create(namespace="ns", key="same")
    services.records.create(payload)
    with pytest.raises(ConflictError):
        services.records.create(make_create(namespace="ns", key="same"))


def test_get(services):
    created = services.records.create(make_create(key="k"))
    fetched = services.records.get(created.id)
    assert fetched.id == created.id
    assert fetched.value == {"n": 1}


def test_get_missing_raises(services):
    with pytest.raises(NotFoundError):
        services.records.get("missing")


def test_put_creates_then_updates(services):
    payload = make_create(namespace="ns", key="k", value={"v": 1})
    created = services.records.put(payload)
    assert created.version == 1

    payload2 = make_create(namespace="ns", key="k", value={"v": 2})
    updated = services.records.put(payload2)
    assert updated.id == created.id
    assert updated.version == 2
    assert updated.value == {"v": 2}
    assert updated.created_at == created.created_at
    assert updated.etag != created.etag


def test_update_partial_bumps_version(services):
    created = services.records.create(make_create(key="k", value={"a": 1}))
    updated = services.records.update(created.id, make_update(value={"a": 2}))
    assert updated.version == 2
    assert updated.value == {"a": 2}
    assert updated.metadata == {}
    assert updated.key == "k"


def test_update_metadata_and_key(services):
    created = services.records.create(make_create(key="old", metadata={"m": 1}))
    updated = services.records.update(
        created.id, make_update(metadata={"m": 2}, key="new")
    )
    assert updated.metadata == {"m": 2}
    assert updated.key == "new"


def test_update_without_fields_rejected(services):
    created = services.records.create(make_create(key="k"))
    with pytest.raises(InvalidRequestError):
        services.records.update(created.id, make_update())


def test_update_missing_raises(services):
    with pytest.raises(NotFoundError):
        services.records.update("missing", make_update(value={"a": 1}))


def test_delete_flow(services):
    created = services.records.create(make_create(key="k"))
    services.records.delete(created.id)
    with pytest.raises(NotFoundError):
        services.records.get(created.id)


def test_list_and_pagination(services):
    for index in range(5):
        services.records.create(
            make_create(namespace="orders", key=f"order-{index}", value={"i": index})
        )
    page = services.records.list(namespace="orders", limit=2, offset=1)
    assert page.total == 5
    assert len(page.items) == 2

    prefixed = services.records.list(namespace="orders", key_prefix="order-3")
    assert prefixed.total == 1


def test_search_matches_key_and_content(services):
    services.records.create(make_create(key="alpha", value={"note": "blue sky"}))
    services.records.create(make_create(key="beta", value={"note": "red sun"}))
    services.records.create(make_create(key="gamma", value={"note": "blue ocean"}))

    by_key = services.records.search(query="alpha")
    assert by_key.total == 1
    assert by_key.items[0].key == "alpha"

    by_content = services.records.search(query="blue")
    assert by_content.total == 2

    by_metadata = services.records.search(query="sun")
    assert by_metadata.total == 1


def test_search_case_insensitive(services):
    services.records.create(make_create(key="MiXeD", value={}))
    result = services.records.search(query="mixed")
    assert result.total == 1


def test_limit_is_clamped(services):
    for index in range(3):
        services.records.create(make_create(namespace="n", key=f"k-{index}"))
    page = services.records.list(namespace="n", limit=10000, offset=-5)
    assert page.limit <= 500
    assert page.offset >= 0
