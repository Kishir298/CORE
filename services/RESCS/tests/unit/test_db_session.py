"""Transaction scope tests."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError, StatementError
from sqlalchemy.pool import StaticPool

from rescs.db.base import Base
from rescs.db.session import create_session_factory, session_scope
from rescs.domain import RecordData
from rescs.errors import ConflictError, DependencyUnavailableError, StorageError
from rescs.models import Record


def make_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


def test_session_scope_commits():
    factory = make_factory()
    record = RecordData(id=str(uuid.uuid4()), namespace="n", key="k", value={"a": 1})
    with session_scope(factory) as session:
        session.add(Record.from_domain(record))
    with factory() as session:
        assert session.get(Record, record.id) is not None


def test_session_scope_rolls_back_on_domain_error():
    factory = make_factory()
    record = RecordData(id=str(uuid.uuid4()), namespace="n", key="k", value={})
    with pytest.raises(ConflictError), session_scope(factory) as session:
        session.add(Record.from_domain(record))
        raise ConflictError("boom")
    with factory() as session:
        assert session.get(Record, record.id) is None


def test_session_scope_conflict_mapping():
    factory = make_factory()
    record = RecordData(
        id=str(uuid.uuid4()), namespace="n", key="k", value={}, idempotency_key="idem"
    )
    with session_scope(factory) as session:
        session.add(Record.from_domain(record))
    duplicate = RecordData(
        id=str(uuid.uuid4()), namespace="n", key="k2", value={}, idempotency_key="idem"
    )
    with pytest.raises(ConflictError) as exc_info:
        with session_scope(factory, conflict=lambda: ConflictError("used")) as session:
            session.add(Record.from_domain(duplicate))
    assert "used" in str(exc_info.value)


def test_session_scope_maps_operational_error_to_dependency():
    class FakeSession:
        def commit(self):
            raise OperationalError("stmt", None, Exception("connection refused"))

        def rollback(self):
            pass

        def close(self):
            pass

    with pytest.raises(DependencyUnavailableError):
        with session_scope(lambda: FakeSession()):
            pass


def test_session_scope_maps_generic_error_to_storage():
    class FakeSession:
        def commit(self):
            raise StatementError("boom", "stmt", None, Exception("boom"))

        def rollback(self):
            pass

        def close(self):
            pass

    with pytest.raises(StorageError), session_scope(lambda: FakeSession()):
        pass
