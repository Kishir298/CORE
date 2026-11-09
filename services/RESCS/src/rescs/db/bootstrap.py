"""Database bootstrap: engine, connectivity, schema, session factory."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, make_url

from rescs.config import Settings
from rescs.db.engine import build_engine, check_connectivity
from rescs.db.schema import SchemaManager
from rescs.db.session import SessionFactory, create_session_factory


@dataclass
class Database:
    engine: Engine
    session_factory: SessionFactory
    backend: str
    schema_version: str | None = None


def bootstrap_database(
    settings: Settings,
    *,
    connect: bool = True,
    create_schema: bool | None = None,
) -> Database:
    """Wire an engine, verify reachability, prepare the schema, and expose a
    session factory.

    :param connect: when true, perform a ``SELECT 1`` connectivity check up
        front and fail fast with a domain error if the database is unreachable.
    :param create_schema: create/migrate tables. Defaults to the value of
        ``settings.auto_create_schema``.
    """
    url = make_url(settings.database_url)
    engine = build_engine(settings.database_url)
    if connect:
        check_connectivity(engine)

    if create_schema is None:
        create_schema = settings.auto_create_schema

    schema_version: str | None = None
    if create_schema:
        manager = SchemaManager(engine)
        manager.migrate()
        schema_version = manager.applied_version()

    return Database(
        engine=engine,
        session_factory=create_session_factory(engine),
        backend=url.get_backend_name(),
        schema_version=schema_version,
    )
