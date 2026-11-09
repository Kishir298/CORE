"""Shared test fixtures.

Environment variables are set at module import time, before any
:class:`rescs.config.Settings` is instantiated, so tests are hermetic.
"""

from __future__ import annotations

import os

os.environ.setdefault("RESCS_API_KEY", "test-api-key-0123456789abcdef")
os.environ.setdefault("RESCS_ENV", "test")
os.environ.setdefault("RESCS_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("RESCS_STORAGE_DIR", "rescs_test_storage")
os.environ.setdefault("RESCS_LOG_LEVEL", "WARNING")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from rescs.config import Settings
from rescs.db.base import Base
from rescs.main import create_app
from rescs.repositories.memory import (
    InMemoryFileObjectRepository,
    InMemoryRecordRepository,
)
from rescs.repositories.sqlalchemy_ import (
    SQLAlchemyFileObjectRepository,
    SQLAlchemyRecordRepository,
)


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(_env_file=None)


@pytest.fixture()
def app(settings: Settings):
    # Use memory storage backend for test isolation
    test_settings = Settings(
        _env_file=None,
        api_key=settings.api_key,
        api_key_owner=settings.api_key_owner,
        database_url=settings.database_url,
        storage_dir=settings.storage_dir,
        storage_backend="memory",
        environment=settings.environment,
        log_level=settings.log_level,
        auto_create_schema=settings.auto_create_schema,
        request_id_header=settings.request_id_header,
        max_records_per_owner=settings.max_records_per_owner,
        max_files_per_owner=settings.max_files_per_owner,
        max_bytes_per_owner=settings.max_bytes_per_owner,
        max_file_size=settings.max_file_size,
        max_metadata_bytes=settings.max_metadata_bytes,
        max_bulk_batch=settings.max_bulk_batch,
        audit_retention_days=settings.audit_retention_days,
        max_ttl_seconds=settings.max_ttl_seconds,
        streaming_threshold_bytes=settings.streaming_threshold_bytes,
        s3_endpoint=settings.s3_endpoint,
        s3_bucket=settings.s3_bucket,
        s3_region=settings.s3_region,
        s3_access_key=settings.s3_access_key,
        s3_secret_key=settings.s3_secret_key,
        s3_path_prefix=settings.s3_path_prefix,
        rate_limit_enabled=settings.rate_limit_enabled,
        rate_limit_general_per_minute=settings.rate_limit_general_per_minute,
        rate_limit_writes_per_minute=settings.rate_limit_writes_per_minute,
        rate_limit_uploads_per_minute=settings.rate_limit_uploads_per_minute,
    )
    return create_app(settings=test_settings)


@pytest.fixture()
def client(app, settings: Settings):
    with TestClient(
        app, headers={"X-API-Key": settings.api_key}
    ) as test_client:
        yield test_client


SCOPED_API_KEY = "scoped-tenant-key-0123456789abcdef"
SCOPED_OWNER = "tenant-a"


@pytest.fixture()
def scoped_app(settings: Settings):
    scoped_settings = Settings(
        _env_file=None,
        api_key=SCOPED_API_KEY,
        api_key_owner=SCOPED_OWNER,
        database_url="sqlite+pysqlite:///:memory:",
        storage_dir="rescs_test_storage",
        storage_backend="memory",
        environment="test",
    )
    return create_app(settings=scoped_settings)


@pytest.fixture()
def scoped_client(scoped_app):
    with TestClient(
        scoped_app, headers={"X-API-Key": SCOPED_API_KEY}
    ) as test_client:
        yield test_client


@pytest.fixture()
def memory_record_repo() -> InMemoryRecordRepository:
    return InMemoryRecordRepository()


@pytest.fixture()
def memory_file_repo() -> InMemoryFileObjectRepository:
    return InMemoryFileObjectRepository()


@pytest.fixture()
def sqlite_session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture()
def sqlalchemy_record_repo(sqlite_session_factory) -> SQLAlchemyRecordRepository:
    return SQLAlchemyRecordRepository(sqlite_session_factory)


@pytest.fixture()
def sqlalchemy_file_repo(sqlite_session_factory) -> SQLAlchemyFileObjectRepository:
    return SQLAlchemyFileObjectRepository(sqlite_session_factory)
