"""ORM model mapping tests (sqlite in-memory)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from rescs.domain import FileObjectData, RecordData
from rescs.models import FileObject, Record


def test_record_round_trip(sqlite_session_factory):
    record = RecordData(
        id=str(uuid.uuid4()),
        namespace="default",
        key="greeting",
        value={"text": "hello"},
        metadata={"lang": "en"},
        owner="alice",
        version=1,
        etag="etag-1",
    )
    with sqlite_session_factory() as session:
        session.add(Record.from_domain(record))
        session.commit()
    with sqlite_session_factory() as session:
        row = session.get(Record, record.id)
        assert row is not None
        domain = row.to_domain()
        assert domain.namespace == "default"
        assert domain.key == "greeting"
        assert domain.value == {"text": "hello"}
        assert domain.metadata == {"lang": "en"}
        assert domain.owner == "alice"
        assert domain.version == 1
        assert domain.etag == "etag-1"
        assert domain.created_at.tzinfo is not None


def test_record_namespace_key_unique(sqlite_session_factory):
    first = RecordData(
        id=str(uuid.uuid4()), namespace="n", key="same", value={"x": 1}
    )
    second = RecordData(
        id=str(uuid.uuid4()), namespace="n", key="same", value={"x": 2}
    )
    with sqlite_session_factory() as session:
        session.add(Record.from_domain(first))
        session.commit()
    with pytest.raises(IntegrityError), sqlite_session_factory() as session:
        session.add(Record.from_domain(second))
        session.commit()


def test_file_object_round_trip(sqlite_session_factory):
    file_obj = FileObjectData(
        id=str(uuid.uuid4()),
        filename="notes.txt",
        mime_type="text/plain",
        size=42,
        storage_path="obj/notes.txt",
        sha256="d" * 64,
        metadata={"m": 1},
    )
    with sqlite_session_factory() as session:
        session.add(FileObject.from_domain(file_obj))
        session.commit()
    with sqlite_session_factory() as session:
        row = session.get(FileObject, file_obj.id)
        domain = row.to_domain()
        assert domain.filename == "notes.txt"
        assert domain.size == 42
        assert domain.sha256 == "d" * 64
        assert domain.storage_path == "obj/notes.txt"
        assert domain.metadata == {"m": 1}


def test_file_object_idempotency_unique(sqlite_session_factory):
    first = FileObjectData(
        id=str(uuid.uuid4()),
        filename="a",
        mime_type="text/plain",
        size=1,
        storage_path="x",
        sha256="a" * 64,
        idempotency_key="same-idem",
    )
    second = FileObjectData(
        id=str(uuid.uuid4()),
        filename="b",
        mime_type="text/plain",
        size=1,
        storage_path="y",
        sha256="b" * 64,
        idempotency_key="same-idem",
    )
    with sqlite_session_factory() as session:
        session.add(FileObject.from_domain(first))
        session.commit()
    with pytest.raises(IntegrityError), sqlite_session_factory() as session:
        session.add(FileObject.from_domain(second))
        session.commit()
