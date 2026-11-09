"""
Persistent storage operations for A.S.I.S. memory.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime

from .database import MemoryDatabase
from .models import Memory, MemoryCategory, MemoryType


def _row_to_memory(row) -> Memory:
    """Convert a SQLite row into a Memory object (tolerates pre-migration DBs)."""
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    return Memory(
        memory_id=row["id"],
        content=row["content"],
        category=MemoryCategory(row["category"]),
        memory_type=MemoryType(row["memory_type"]),
        importance=row["importance"],
        metadata=json.loads(row["metadata"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        identity_id=row["identity_id"] if "identity_id" in keys else "default",
        confidence=float(row["confidence"]) if "confidence" in keys else 0.7,
        source=row["source"] if "source" in keys else "user-stated",
        evidence=row["evidence"] if "evidence" in keys else "",
    )


class MemoryStorage:
    """CRUD operations for persistent memories."""

    def __init__(self, database: MemoryDatabase) -> None:
        self.database = database

    def save(self, memory: Memory) -> Memory:
        """Save a memory and return it with its database ID."""
        connection = self.database._connect()

        try:
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO memories (
                        content, category, memory_type, importance, metadata,
                        created_at, updated_at, identity_id, confidence, source, evidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (memory.content, memory.category.value, memory.memory_type.value,
                     memory.importance, json.dumps(memory.metadata),
                     memory.created_at.isoformat(), memory.updated_at.isoformat(),
                     memory.identity_id, memory.confidence, memory.source, memory.evidence),
                )
            except Exception:
                cursor = connection.execute(
                    """
                    INSERT INTO memories (
                        content, category, memory_type, importance, metadata,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (memory.content, memory.category.value, memory.memory_type.value,
                     memory.importance, json.dumps(memory.metadata),
                     memory.created_at.isoformat(), memory.updated_at.isoformat()),
                )

            connection.commit()
            memory_id = cursor.lastrowid

        finally:
            connection.close()

        return replace(memory, memory_id=memory_id)

    def get(self, memory_id: int) -> Memory | None:
        """Retrieve a memory by ID."""
        connection = self.database._connect()

        try:
            row = connection.execute(
                """
                SELECT *
                FROM memories
                WHERE id = ?
                """,
                (memory_id,),
            ).fetchone()

        finally:
            connection.close()

        if row is None:
            return None

        return _row_to_memory(row)

    def update(self, memory: Memory) -> Memory | None:
        """Update an existing memory. Returns None when missing."""
        if memory.memory_id is None:
            return None

        connection = self.database._connect()

        try:
            cursor = connection.execute(
                """
                UPDATE memories
                SET content = ?,
                    category = ?,
                    memory_type = ?,
                    importance = ?,
                    metadata = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    memory.content,
                    memory.category.value,
                    memory.memory_type.value,
                    memory.importance,
                    json.dumps(memory.metadata),
                    datetime.now(UTC).isoformat(),
                    memory.memory_id,
                ),
            )

            connection.commit()
            updated = cursor.rowcount > 0

        finally:
            connection.close()

        if not updated:
            return None

        return self.get(memory.memory_id)

    def delete(self, memory_id: int) -> bool:
        """Delete a memory by ID."""
        connection = self.database._connect()

        try:
            cursor = connection.execute(
                """
                DELETE FROM memories
                WHERE id = ?
                """,
                (memory_id,),
            )

            connection.commit()
            deleted = cursor.rowcount > 0

        finally:
            connection.close()

        return deleted

    def clear(self) -> int:
        """Delete all memories. Returns the number removed."""
        connection = self.database._connect()

        try:
            cursor = connection.execute(
                """
                DELETE FROM memories
                """
            )

            connection.commit()
            count = cursor.rowcount

        finally:
            connection.close()

        return count

    def list_all(
        self,
        category: MemoryCategory | None = None,
    ) -> list[Memory]:
        """Return all stored memories, optionally filtered."""
        if category is not None:
            query = (
                "SELECT * FROM memories WHERE category = ? "
                "ORDER BY importance DESC, created_at DESC"
            )
            params: tuple = (category.value,)
        else:
            query = "SELECT * FROM memories ORDER BY importance DESC, created_at DESC"
            params = ()

        connection = self.database._connect()

        try:
            rows = connection.execute(query, params).fetchall()

        finally:
            connection.close()

        return [_row_to_memory(row) for row in rows]

    def search(
        self,
        query: str,
        category: MemoryCategory | None = None,
    ) -> list[Memory]:
        """Perform a basic text search over memory content."""
        query = query.strip()

        if not query:
            return []

        if category is not None:
            sql = (
                "SELECT * FROM memories WHERE content LIKE ? "
                "AND category = ? "
                "ORDER BY importance DESC, created_at DESC"
            )
            params: tuple = (f"%{query}%", category.value)
        else:
            sql = (
                "SELECT * FROM memories WHERE content LIKE ? "
                "ORDER BY importance DESC, created_at DESC"
            )
            params = (f"%{query}%",)

        connection = self.database._connect()

        try:
            rows = connection.execute(sql, params).fetchall()

        finally:
            connection.close()

        return [_row_to_memory(row) for row in rows]
