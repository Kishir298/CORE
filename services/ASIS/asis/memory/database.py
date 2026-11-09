"""
SQLite database layer for A.S.I.S. memory.

The database lives in A.S.I.S.' persistent data directory, outside the
repository. Cloud persistence is owned by R.E.S.C.S. and is not used
here.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


class MemoryDatabase:
    """SQLite database used by the memory subsystem."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=10,
        )
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        """Create required database tables and indexes."""
        connection = self._connect()

        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    importance INTEGER NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memories_category
                ON memories(category)
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memories_importance
                ON memories(importance)
                """
            )

            for ddl in (
                "ALTER TABLE memories ADD COLUMN identity_id TEXT NOT NULL DEFAULT 'default'",
                "ALTER TABLE memories ADD COLUMN confidence REAL NOT NULL DEFAULT 0.7",
                "ALTER TABLE memories ADD COLUMN source TEXT NOT NULL DEFAULT 'user-stated'",
                "ALTER TABLE memories ADD COLUMN evidence TEXT NOT NULL DEFAULT ''",
                """CREATE TABLE IF NOT EXISTS memory_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, identity_id TEXT,
                    memory_id INTEGER, ts TEXT, op TEXT, reason TEXT)""",
            ):
                try:
                    connection.execute(ddl)
                except Exception:
                    pass
            try:
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_memories_identity ON memories(identity_id)"
                )
            except Exception:
                pass

            connection.commit()

        finally:
            connection.close()
