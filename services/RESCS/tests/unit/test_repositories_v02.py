"""v0.2 repository parity: memory and SQLAlchemy backends behave identically
for soft delete, expiry, tags, occupants, and quota accounting."""

from __future__ import annotations

from datetime import timedelta

import pytest

from rescs.domain import utcnow
from rescs.errors import NotFoundError
from rescs.repositories.memory import (
    InMemoryFileObjectRepository,
    InMemoryRecordRepository,
)
from rescs.repositories.sqlalchemy_ import (
    SQLAlchemyFileObjectRepository,
    SQLAlchemyRecordRepository,
)
from rescs.schemas.record import RecordCreate
from rescs.services.records import RecordService


@pytest.fixture(params=["memory", "sqlalchemy"])
def record_repo(request, sqlite_session_factory):
    if request.param == "memory":
        return InMemoryRecordRepository()
    return SQLAlchemyRecordRepository(sqlite_session_factory)


@pytest.fixture(params=["memory", "sqlalchemy"])
def file_repo(request, sqlite_session_factory):
    if request.param == "memory":
        return InMemoryFileObjectRepository()
    return SQLAlchemyFileObjectRepository(sqlite_session_factory)


def _record(key="k", **overrides):
    values = dict(namespace="ns", key=key, value={"v": 1})
    values.update(overrides)
    return RecordCreate(**values)


def test_soft_deleted_hidden_from_get_but_visible_including_deleted(record_repo):
    service = RecordService(record_repo)
    created = service.create(_record())
    service.delete(created.id, actor="owner-A")
    with pytest.raises(NotFoundError):
        service.get(created.id)
    tombstone = service.get_including_deleted(created.id)
    assert tombstone.deleted_at is not None
    assert tombstone.deleted_by == "owner-A"
    assert service.list_deleted().total == 1
    assert service.list().total == 0


def test_key_reusable_while_tombstone_exists(record_repo):
    service = RecordService(record_repo)
    first = service.create(_record(key="reuse"))
    service.delete(first.id)
    second = service.create(_record(key="reuse", value={"gen": 2}))
    assert second.id != first.id
    assert service.get(second.id).value == {"gen": 2}


def test_expired_invisible_and_reclaimed(record_repo):
    service = RecordService(record_repo)
    created = service.create(
        _record(key="exp", expires_at=utcnow() + timedelta(hours=1))
    )
    # Age the row past expiry directly through the repository seam.
    row = record_repo.get_including_deleted(created.id)
    row.expires_at = utcnow() - timedelta(seconds=1)
    record_repo.update(row)
    with pytest.raises(NotFoundError):
        service.get(created.id)
    assert service.list().total == 0
    # A fresh create reclaims the expired occupant instead of conflicting.
    fresh = service.create(_record(key="exp", value={"gen": 2}))
    assert fresh.id != created.id


def test_tags_filter_and_counts(record_repo):
    service = RecordService(record_repo)
    service.create(_record(key="a", tags=["x", "y"]))
    service.create(_record(key="b", tags=["x"]))
    assert service.list(tags=["x"]).total == 2
    assert service.list(tags=["x", "y"]).total == 1
    assert service.list(tags=["nope"]).total == 0
    assert record_repo.count_by_owner("system") == 2


def test_time_window_filters(record_repo):
    service = RecordService(record_repo)
    service.create(_record(key="w"))
    now = utcnow()
    assert service.list(created_before=now + timedelta(seconds=1)).total == 1
    assert service.list(created_after=now + timedelta(seconds=1)).total == 0
    assert service.list(updated_before=now + timedelta(seconds=1)).total == 1


def test_find_occupant_sees_beyond_live_view(record_repo):
    service = RecordService(record_repo)
    created = service.create(_record(key="occ"))
    assert record_repo.find_occupant("ns", "occ").id == created.id
    service.delete(created.id)
    assert record_repo.get_by_namespace_key("ns", "occ") is None
    assert record_repo.find_occupant("ns", "occ").id == created.id


def test_file_expiry_and_byte_accounting(file_repo):
    from rescs.schemas.file_object import FileObjectCreate
    from rescs.services.files import FileService
    from rescs.storage.memory import MemoryObjectStore

    service = FileService(file_repo, MemoryObjectStore())
    one = service.create(FileObjectCreate(filename="a.bin"), b"a" * 10)
    two = service.create(
        FileObjectCreate(filename="b.bin"),
        b"b" * 20,
    )
    assert file_repo.count_by_owner("system") == 2
    assert file_repo.bytes_by_owner("system") == 30
    service.delete(one.id)
    assert file_repo.count_by_owner("system") == 1
    assert file_repo.bytes_by_owner("system") == 20
    assert file_repo.count_by_owner("system", include_deleted=True) == 2
    assert [item.id for item in file_repo.list_expired(utcnow() + timedelta(seconds=1))] == []
    # Expire the remaining file and confirm the expired listing.
    row = file_repo.get_including_deleted(two.id)
    row.expires_at = utcnow() - timedelta(seconds=1)
    file_repo.update(row)
    expired = file_repo.list_expired(utcnow(), limit=10)
    assert [item.id for item in expired] == [two.id]


def test_etag_stable_without_tags_and_sorted_with_tags():
    from rescs.etag import content_etag

    assert content_etag({"a": 1}, {}) == content_etag({"a": 1}, {})
    assert content_etag({"a": 1}, {}, ["x", "y"]) == content_etag({"a": 1}, {}, ["y", "x"])
    assert content_etag({"a": 1}, {}) != content_etag({"a": 1}, {}, ["x"])

