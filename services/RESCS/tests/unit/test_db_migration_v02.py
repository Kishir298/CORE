"""v0.2 migration tests: pre-v0.2 databases upgrade without data loss."""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from rescs.db.schema import SchemaManager

V01_RECORDS_DDL = """
CREATE TABLE records (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    namespace VARCHAR(128) NOT NULL,
    "key" VARCHAR(512) NOT NULL,
    value JSON NOT NULL,
    metadata JSON NOT NULL,
    owner VARCHAR(256) NOT NULL,
    version INTEGER NOT NULL,
    idempotency_key VARCHAR(128),
    etag VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_records_namespace_key UNIQUE (namespace, "key"),
    CONSTRAINT uq_records_idempotency UNIQUE (idempotency_key)
)
"""

V01_FILES_DDL = """
CREATE TABLE file_objects (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    filename VARCHAR(512) NOT NULL,
    mime_type VARCHAR(128) NOT NULL,
    size BIGINT NOT NULL,
    storage_path VARCHAR(1024) NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    metadata JSON NOT NULL,
    owner VARCHAR(256) NOT NULL,
    version INTEGER NOT NULL,
    idempotency_key VARCHAR(128),
    etag VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
)
"""


def _v01_engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/legacy.db",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.execute(text(V01_RECORDS_DDL))
        connection.execute(text(V01_FILES_DDL))
        connection.execute(
            text(
                "INSERT INTO records (id, namespace, key, value, metadata,"
                " owner, version, etag, created_at, updated_at)"
                " VALUES ('r-1', 'ns', 'k', '{\"a\": 1}', '{}', 'system',"
                " 1, 'etag-1', '2024-01-01T00:00:00+00:00',"
                " '2024-01-01T00:00:00+00:00')"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE schema_info (key VARCHAR PRIMARY KEY,"
                " value VARCHAR NOT NULL)"
            )
        )
        connection.execute(
            text("INSERT INTO schema_info (key, value) VALUES ('version', '0.1.0')")
        )
    return engine


def test_v01_sqlite_upgrades_without_data_loss(tmp_path):
    engine = _v01_engine(tmp_path)
    try:
        manager = SchemaManager(engine)
        manager.migrate()
        assert manager.applied_version() == SchemaManager.SCHEMA_VERSION
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT id, namespace, key, version, etag, tags,"
                    " expires_at, deleted_at, deleted_by FROM records"
                )
            ).first()
            assert row is not None
            assert row[0] == "r-1" and row[3] == 1 and row[4] == "etag-1"
            assert row[5] in ("[]", "[]")  # defaulted empty tag list
            assert row[6] is None and row[7] is None and row[8] is None
            # Legacy helper table is gone.
            tables = connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).all()
            names = {t[0] for t in tables}
            assert "records_legacy_v01" not in names
            assert "audit_events" in names
        # Second migrate is idempotent.
        manager.migrate()
        assert manager.applied_version() == SchemaManager.SCHEMA_VERSION
    finally:
        engine.dispose()


def test_fresh_database_gets_v02_schema(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/fresh.db",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        manager = SchemaManager(engine)
        manager.migrate()
        assert manager.applied_version() == SchemaManager.SCHEMA_VERSION
        with engine.connect() as connection:
            indexes = connection.execute(
                text("SELECT name, sql FROM sqlite_master WHERE type='index'")
            ).all()
            partial = [sql for name, sql in indexes if name == "uq_records_live_namespace_key"]
            assert partial and "WHERE" in partial[0].upper()
    finally:
        engine.dispose()

