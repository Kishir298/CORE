"""Schema creation and lightweight versioned migration."""

from __future__ import annotations

from sqlalchemy import Engine, inspect, text


class SchemaManager:
    """Ensure the application schema exists and track its version.

    Table DDL is derived from the ORM metadata. A ``schema_info`` table
    records the applied schema version; running ``migrate`` repeatedly is
    idempotent. This covers development and lightweight deployments;
    heavily versioned production schemas may adopt a migration tool such as
    Alembic on top of this foundation.
    """

    SCHEMA_VERSION = "0.3.0"

    # v0.2 additive columns (records + file_objects). All nullable or
    # defaulted so existing rows migrate without data loss.
    _V02_COLUMNS: tuple[tuple[str, str, str], ...] = (
        # (column, sqlite ddl, postgres ddl)
        ("tags", "JSON", "JSON"),
        ("expires_at", "TIMESTAMP", "TIMESTAMPTZ"),
        ("deleted_at", "TIMESTAMP", "TIMESTAMPTZ"),
        ("deleted_by", "VARCHAR(256)", "VARCHAR(256)"),
    )

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def migrate(self) -> None:
        import rescs.models

        Base = rescs.models.Base
        if self._needs_v02_upgrade():
            backend = self._engine.url.get_backend_name()
            if backend.startswith("sqlite"):
                self._upgrade_sqlite(Base)
            else:
                self._upgrade_postgres()
        else:
            Base.metadata.create_all(self._engine)
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS schema_info "
                    "(key VARCHAR PRIMARY KEY, value VARCHAR NOT NULL)"
                )
            )

        with self._engine.begin() as connection:
            existing = connection.execute(
                text("SELECT value FROM schema_info WHERE key = 'version'")
            ).first()
            if existing is None:
                connection.execute(
                    text(
                        "INSERT INTO schema_info (key, value) "
                        "VALUES ('version', :version)"
                    ),
                    {"version": self.SCHEMA_VERSION},
                )
            else:
                connection.execute(
                    text("UPDATE schema_info SET value = :version WHERE key = 'version'"),
                    {"version": self.SCHEMA_VERSION},
                )

    def applied_version(self) -> str | None:
        with self._engine.connect() as connection:
            if not inspect(connection).has_table("schema_info"):
                return None
            result = connection.execute(
                text("SELECT value FROM schema_info WHERE key = 'version'")
            ).first()
            return result[0] if result is not None else None

    def _needs_v02_upgrade(self) -> bool:
        """Detect a pre-v0.2 database (records table without v0.2 columns)."""
        with self._engine.connect() as connection:
            inspector = inspect(connection)
            if not inspector.has_table("records"):
                return False
            columns = {col["name"] for col in inspector.get_columns("records")}
            return "deleted_at" not in columns

    def _add_v02_columns(self, connection, table: str, dialect: str) -> None:
        existing = {
            col["name"] for col in inspect(connection).get_columns(table)
        }
        for name, sqlite_ddl, postgres_ddl in self._V02_COLUMNS:
            if name in existing:
                continue
            ddl = sqlite_ddl if dialect == "sqlite" else postgres_ddl
            keyword = "ADD COLUMN" if dialect == "sqlite" else "ADD COLUMN IF NOT EXISTS"
            connection.execute(text(f"ALTER TABLE {table} {keyword} {name} {ddl}"))

    def _upgrade_sqlite(self, Base) -> None:
        """Rebuild ``records`` (drops the v0.1 full unique constraint in favour
        of the live-only partial index) and add v0.2 columns elsewhere."""
        with self._engine.begin() as connection:
            connection.execute(text("ALTER TABLE records RENAME TO records_legacy_v01"))
        Base.metadata.create_all(self._engine)
        with self._engine.begin() as connection:
            self._add_v02_columns(connection, "file_objects", "sqlite")
            connection.execute(
                text(
                    "INSERT INTO records (id, namespace, key, value, metadata,"
                    " owner, version, idempotency_key, etag, created_at,"
                    " updated_at, tags, expires_at, deleted_at, deleted_by)"
                    " SELECT id, namespace, key, value, metadata, owner,"
                    " version, idempotency_key, etag, created_at, updated_at,"
                    " '[]', NULL, NULL, NULL FROM records_legacy_v01"
                )
            )
            connection.execute(text("DROP TABLE records_legacy_v01"))

    def _upgrade_postgres(self) -> None:
        import rescs.models

        Base = rescs.models.Base
        Base.metadata.create_all(self._engine)
        with self._engine.begin() as connection:
            self._add_v02_columns(connection, "records", "postgres")
            self._add_v02_columns(connection, "file_objects", "postgres")
            connection.execute(
                text(
                    "ALTER TABLE records DROP CONSTRAINT IF EXISTS"
                    " uq_records_namespace_key"
                )
            )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS"
                    " uq_records_live_namespace_key ON records (namespace, key)"
                    " WHERE deleted_at IS NULL"
                )
            )
