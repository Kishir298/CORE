"""Integration: PostgreSQL compatibility gate (§9, §24).

SQLite stays the deterministic default for ordinary tests. These tests only
execute when ``RESCS_INTEGRATION_DATABASE_URL`` points at a live PostgreSQL
(Supabase-compatible) instance; otherwise they skip cleanly. They never
silently fall back to SQLite when Postgres was explicitly requested.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import make_url

from rescs.config import Settings
from rescs.db.bootstrap import bootstrap_database
from rescs.db.engine import build_engine, check_connectivity
from rescs.repositories.memory import InMemoryFileObjectRepository
from rescs.repositories.sqlalchemy_ import SQLAlchemyRecordRepository
from rescs.schemas.record import RecordCreate
from rescs.services.files import FileService
from rescs.services.records import RecordService
from rescs.storage.memory import MemoryObjectStore

INTEGRATION_URL = os.environ.get("RESCS_INTEGRATION_DATABASE_URL", "")

requires_postgres = pytest.mark.skipif(
    not INTEGRATION_URL,
    reason="RESCS_INTEGRATION_DATABASE_URL not configured; Postgres check deferred",
)


def test_postgres_gate_skips_cleanly_when_unconfigured():
    if INTEGRATION_URL:
        pytest.skip("integration database configured; gate test not applicable")
    assert INTEGRATION_URL == ""


@requires_postgres
def test_postgres_url_is_really_postgres():
    url = make_url(INTEGRATION_URL)
    assert url.get_backend_name() in ("postgresql", "postgres"), (
        f"RESCS_INTEGRATION_DATABASE_URL must be PostgreSQL, got {url.get_backend_name()}"
    )


@requires_postgres
def test_postgres_connectivity_and_schema():
    settings = Settings(
        _env_file=None,
        api_key="test-api-key-0123456789abcdef",
        database_url=INTEGRATION_URL,
        environment="test",
    )
    engine = build_engine(INTEGRATION_URL)
    try:
        check_connectivity(engine)  # raises DEPENDENCY_UNAVAILABLE if down
    finally:
        engine.dispose()
    database = bootstrap_database(settings)
    try:
        assert database.backend in ("postgresql", "postgres")
        assert database.schema_version
    finally:
        database.engine.dispose()


@requires_postgres
def test_postgres_record_crud_smoke():
    settings = Settings(
        _env_file=None,
        api_key="test-api-key-0123456789abcdef",
        database_url=INTEGRATION_URL,
        environment="test",
    )
    database = bootstrap_database(settings)
    try:
        records = RecordService(SQLAlchemyRecordRepository(database.session_factory))
        created = records.create(
            RecordCreate(namespace="pg.smoke", key="k1", value={"hello": "postgres"})
        )
        assert created.version == 1 and created.etag
        reread = records.get(created.id)
        assert reread.value == {"hello": "postgres"}
        # Files service is exercised with the memory store here; the Postgres
        # assertion is about the metadata/repository path, blobs stay pluggable.
        files = FileService(InMemoryFileObjectRepository(), MemoryObjectStore())
        assert files.object_store is not None
    finally:
        database.engine.dispose()

