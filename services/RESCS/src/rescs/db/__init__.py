"""Database wiring: engine, sessions, schema, bootstrap."""

from __future__ import annotations

from rescs.db.bootstrap import Database, bootstrap_database
from rescs.db.engine import build_engine, check_connectivity
from rescs.db.schema import SchemaManager
from rescs.db.session import SessionFactory, create_session_factory, session_scope

__all__ = [
    "Database",
    "SchemaManager",
    "SessionFactory",
    "bootstrap_database",
    "build_engine",
    "check_connectivity",
    "create_session_factory",
    "session_scope",
]
