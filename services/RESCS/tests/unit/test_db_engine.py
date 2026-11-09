"""Engine construction and connectivity tests."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect
from sqlalchemy.pool import StaticPool

from rescs.db.engine import build_engine, check_connectivity
from rescs.errors import DependencyUnavailableError


def test_sqlite_memory_uses_static_pool():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    assert isinstance(engine.pool, StaticPool)
    with engine.connect():
        pass


def test_sqlite_file_engine():
    engine = build_engine("sqlite+pysqlite:///rescs_dev.db")
    assert engine.url.get_backend_name() == "sqlite"
    assert not isinstance(engine.pool, StaticPool)


def test_postgres_engine_gets_pool_pre_ping():
    engine = build_engine("postgresql+psycopg://u:p@localhost:5432/db")
    assert engine.pool._pre_ping is True
    assert engine.url.get_backend_name() == "postgresql"


def test_check_connectivity_ok_on_sqlite():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    check_connectivity(engine)


def test_check_connectivity_unreachable_raises_domain_error():
    engine = build_engine(
        "postgresql+psycopg://invalid:invalid@127.0.0.1:1/nope",
        connect_timeout=1,
    )
    with pytest.raises(DependencyUnavailableError):
        check_connectivity(engine)


def test_sqlite_user_has_sqlite_tables_creatable():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    from rescs import models  # noqa: F401
    from rescs.db.base import Base

    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    assert "records" in inspector.get_table_names()
    assert "file_objects" in inspector.get_table_names()
