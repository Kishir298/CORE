"""Database bootstrap tests, including real persistent file-backed storage."""

from __future__ import annotations

import uuid

import pytest

from rescs.config import Settings
from rescs.db.bootstrap import bootstrap_database
from rescs.domain import RecordData
from rescs.errors import DependencyUnavailableError
from rescs.repositories.sqlalchemy_ import SQLAlchemyRecordRepository


def make_settings(**overrides) -> Settings:
    values = dict(
        api_key="test-api-key-0123456789abcdef",
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        storage_dir="rescs_test_storage",
        auto_create_schema=True,
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_bootstrap_sqlite_memory():
    database = bootstrap_database(make_settings())
    assert database.backend == "sqlite"
    assert database.schema_version is not None
    assert database.session_factory is not None
    database.engine.dispose()


def test_bootstrap_unreachable_database_raises():
    settings = make_settings(
        database_url="postgresql+psycopg://invalid:invalid@127.0.0.1:1/nope"
    )
    with pytest.raises(DependencyUnavailableError):
        bootstrap_database(settings)


def test_persistent_record_storage(tmp_path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'rescs_persist.db'}"
    settings = make_settings(database_url=database_url)

    database = bootstrap_database(settings)
    repo = SQLAlchemyRecordRepository(database.session_factory)
    record = RecordData(
        id=str(uuid.uuid4()),
        namespace="persist",
        key="doc",
        value={"version": 1},
        metadata={"source": "test"},
        owner="alice",
    )
    repo.create(record)
    database.engine.dispose()

    reopened = bootstrap_database(make_settings(database_url=database_url))
    repo2 = SQLAlchemyRecordRepository(reopened.session_factory)
    fetched = repo2.get(record.id)
    assert fetched.value == {"version": 1}
    assert fetched.metadata == {"source": "test"}
    assert fetched.owner == "alice"
    reopened.engine.dispose()


def test_bootstrap_respects_no_schema_creation():
    database = bootstrap_database(make_settings(auto_create_schema=False))
    assert database.schema_version is None
    database.engine.dispose()
