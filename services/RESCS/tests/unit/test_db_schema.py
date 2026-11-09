"""SchemaManager migration tests."""

from __future__ import annotations

from sqlalchemy import inspect

from rescs.db.engine import build_engine
from rescs.db.schema import SchemaManager


def make_engine():
    return build_engine("sqlite+pysqlite:///:memory:")


def test_migrate_creates_tables_and_version():
    engine = make_engine()
    manager = SchemaManager(engine)
    assert manager.applied_version() is None

    manager.migrate()

    inspector = inspect(engine)
    assert "schema_info" in inspector.get_table_names()
    assert "records" in inspector.get_table_names()
    assert "file_objects" in inspector.get_table_names()
    assert manager.applied_version() == SchemaManager.SCHEMA_VERSION


def test_migrate_is_idempotent():
    engine = make_engine()
    manager = SchemaManager(engine)
    manager.migrate()
    manager.migrate()
    assert manager.applied_version() == SchemaManager.SCHEMA_VERSION


def test_applied_version_tracks_current():
    engine = make_engine()
    first = SchemaManager(engine)
    first.migrate()
    second = SchemaManager(engine)
    assert second.applied_version() == first.SCHEMA_VERSION
