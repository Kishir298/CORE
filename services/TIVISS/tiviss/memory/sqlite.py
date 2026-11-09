"""Dual SQLite memory store for T.I.V.I.S.S.

Provides two separate databases:
- conversation_logs.db: Append-only conversation history (request/response pairs)
- semantic_memory.db: Structured long-term memory (facts, preferences, context)
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .interface import MemoryRecord, MemorySearchResult, MemoryKeyError


@dataclass
class ConversationLogEntry:
    """A single conversation log entry."""
    log_id: int
    request_id: str
    request_content: str
    response_content: str
    metadata: dict[str, Any]
    created_at: float


@dataclass
class SemanticMemoryEntry:
    """A single semantic memory entry."""
    record_id: str
    content: str
    category: str
    memory_type: str
    importance: int
    confidence: float
    source: str
    evidence: str
    metadata: dict[str, Any]
    created_at: float
    updated_at: float


def _now_dt() -> datetime:
    """Return current timezone-aware datetime."""
    return datetime.now(UTC)


def _dt_to_float(dt: datetime) -> float:
    """Convert datetime to float timestamp."""
    return dt.timestamp()


def _float_to_dt(ts: float) -> datetime:
    """Convert float timestamp to timezone-aware datetime."""
    return datetime.fromtimestamp(ts, UTC)


def _extract_metadata_cols(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Extract structured metadata columns from metadata dict."""
    return {
        "category": metadata.get("category", "general"),
        "memory_type": metadata.get("memory_type", "fact"),
        "importance": metadata.get("importance", 5),
        "confidence": metadata.get("confidence", 0.7),
        "source": metadata.get("source", "user-stated"),
        "evidence": metadata.get("evidence", ""),
    }


def _build_metadata_json(metadata: Mapping[str, Any]) -> str:
    """Build metadata JSON excluding structured columns."""
    excluded = {"category", "memory_type", "importance", "confidence", "source", "evidence"}
    return json.dumps({k: v for k, v in metadata.items() if k not in excluded})


def _merge_metadata(json_str: str, cols: dict[str, Any]) -> dict[str, Any]:
    """Merge metadata JSON with structured columns, JSON takes precedence."""
    metadata = json.loads(json_str) if json_str else {}
    # Start with column values as defaults
    result = dict(cols)
    # Override with JSON values (which are newer if update() was called)
    result.update(metadata)
    return result


class SQLiteMemoryStore:
    """Dual SQLite memory store with separate conversation and semantic databases."""

    def __init__(
        self,
        conversation_db: str,
        semantic_db: str,
        autosave: bool = True,
    ) -> None:
        self.conversation_db = Path(conversation_db)
        self.semantic_db = Path(semantic_db)
        self.autosave = autosave

        # Ensure parent directories exist
        self.conversation_db.parent.mkdir(parents=True, exist_ok=True)
        self.semantic_db.parent.mkdir(parents=True, exist_ok=True)

        self._init_conversation_db()
        self._init_semantic_db()

    def _init_conversation_db(self) -> None:
        """Initialize the conversation logs database."""
        with sqlite3.connect(self.conversation_db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation_logs (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    request_content TEXT NOT NULL,
                    response_content TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversation_request_id
                ON conversation_logs(request_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversation_created_at
                ON conversation_logs(created_at)
            """)

    def _init_semantic_db(self) -> None:
        """Initialize the semantic memory database with migration support."""
        with sqlite3.connect(self.semantic_db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS semantic_memory (
                    record_id TEXT PRIMARY KEY,
                    key TEXT NOT NULL,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    importance INTEGER NOT NULL DEFAULT 5,
                    confidence REAL NOT NULL DEFAULT 0.7,
                    source TEXT NOT NULL DEFAULT 'user-stated',
                    evidence TEXT NOT NULL DEFAULT '',
                    metadata TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            
            # Migration: add key column if missing (for older databases)
            cursor = conn.execute("PRAGMA table_info(semantic_memory)")
            columns = [row[1] for row in cursor.fetchall()]
            if "key" not in columns:
                conn.execute("ALTER TABLE semantic_memory ADD COLUMN key TEXT NOT NULL DEFAULT ''")
                # Backfill key with record_id for existing records
                conn.execute("UPDATE semantic_memory SET key = record_id WHERE key = ''")
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_semantic_category
                ON semantic_memory(category)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_semantic_memory_type
                ON semantic_memory(memory_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_semantic_importance
                ON semantic_memory(importance)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_semantic_created_at
                ON semantic_memory(created_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_semantic_key
                ON semantic_memory(key)
            """)

    # --- Conversation Log Methods ---

    def append_conversation(
        self,
        request_id: str,
        request_content: str,
        response_content: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Append a conversation exchange to the log."""
        metadata = metadata or {}
        created_at = _now_dt()
        with sqlite3.connect(self.conversation_db) as conn:
            cursor = conn.execute(
                """
                INSERT INTO conversation_logs
                (request_id, request_content, response_content, metadata, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (request_id, request_content, response_content, json.dumps(metadata), _dt_to_float(created_at)),
            )
            return cursor.lastrowid

    def get_conversation_history(
        self,
        limit: int = 100,
        session_id: str | None = None,
    ) -> list[ConversationLogEntry]:
        """Get recent conversation history."""
        query = "SELECT log_id, request_id, request_content, response_content, metadata, created_at FROM conversation_logs"
        params: list[Any] = []
        if session_id:
            query += " WHERE request_id LIKE ?"
            params.append(f"{session_id}%")
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.conversation_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
        return [
            ConversationLogEntry(
                log_id=row["log_id"],
                request_id=row["request_id"],
                request_content=row["request_content"],
                response_content=row["response_content"],
                metadata=json.loads(row["metadata"]),
                created_at=_float_to_dt(row["created_at"]),
            )
            for row in rows
        ]

    def search_conversation(
        self,
        query: str,
        limit: int = 10,
    ) -> list[ConversationLogEntry]:
        """Search conversation history by content."""
        search_term = f"%{query}%"
        with sqlite3.connect(self.conversation_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT log_id, request_id, request_content, response_content, metadata, created_at
                FROM conversation_logs
                WHERE request_content LIKE ? OR response_content LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (search_term, search_term, limit),
            ).fetchall()
        return [
            ConversationLogEntry(
                log_id=row["log_id"],
                request_id=row["request_id"],
                request_content=row["request_content"],
                response_content=row["response_content"],
                metadata=json.loads(row["metadata"]),
                created_at=_float_to_dt(row["created_at"]),
            )
            for row in rows
        ]

    # --- Semantic Memory Methods (implements MemoryBackend interface) ---

    def store(self, record: MemoryRecord) -> MemoryRecord:
        """Store a memory record in semantic memory."""
        now = _now_dt()
        record_id = record.record_id if record.record_id else str(uuid.uuid4())
        
        # Extract structured columns from metadata
        meta_cols = _extract_metadata_cols(record.metadata)
        metadata_json = _build_metadata_json(record.metadata)

        with sqlite3.connect(self.semantic_db) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO semantic_memory
                (record_id, key, content, category, memory_type, importance, confidence,
                 source, evidence, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    record.key,
                    record.content,
                    meta_cols["category"],
                    meta_cols["memory_type"],
                    meta_cols["importance"],
                    meta_cols["confidence"],
                    meta_cols["source"],
                    meta_cols["evidence"],
                    metadata_json,
                    _dt_to_float(record.created_at),
                    _dt_to_float(now),
                ),
            )
        return MemoryRecord(
            key=record.key,
            content=record.content,
            record_id=record_id,
            metadata={**record.metadata, "record_id": record_id},
            created_at=record.created_at,
            updated_at=now,
        )

    def retrieve(self, record_id: str) -> MemoryRecord:
        """Retrieve a memory record by ID."""
        with sqlite3.connect(self.semantic_db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM semantic_memory WHERE record_id = ?",
                (record_id,),
            ).fetchone()
        if not row:
            raise MemoryKeyError(record_id)
        
        metadata = _merge_metadata(row["metadata"], {
            "category": row["category"],
            "memory_type": row["memory_type"],
            "importance": row["importance"],
            "confidence": row["confidence"],
            "source": row["source"],
            "evidence": row["evidence"],
        })
        
        return MemoryRecord(
            key=row["key"],
            content=row["content"],
            record_id=row["record_id"],
            metadata=metadata,
            created_at=_float_to_dt(row["created_at"]),
            updated_at=_float_to_dt(row["updated_at"]),
        )

    def update(
        self,
        record_id: str,
        content: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> bool:
        """Update a memory record."""
        with sqlite3.connect(self.semantic_db) as conn:
            conn.row_factory = sqlite3.Row
            # Get existing
            row = conn.execute(
                "SELECT content, metadata, category, memory_type, importance, confidence, source, evidence FROM semantic_memory WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            if not row:
                return False

            old_content = row["content"]
            old_metadata = json.loads(row["metadata"]) if row["metadata"] else {}
            
            # Merge old metadata with new metadata
            new_metadata = dict(old_metadata)
            if metadata:
                new_metadata.update(metadata)
            
            # Extract structured columns from merged metadata
            meta_cols = _extract_metadata_cols(new_metadata)
            metadata_json = _build_metadata_json(new_metadata)
            
            new_content = content if content is not None else old_content
            now = _now_dt()

            conn.execute(
                """
                UPDATE semantic_memory
                SET content = ?, category = ?, memory_type = ?, importance = ?,
                    confidence = ?, source = ?, evidence = ?, metadata = ?, updated_at = ?
                WHERE record_id = ?
                """,
                (
                    new_content,
                    meta_cols["category"],
                    meta_cols["memory_type"],
                    meta_cols["importance"],
                    meta_cols["confidence"],
                    meta_cols["source"],
                    meta_cols["evidence"],
                    metadata_json,
                    _dt_to_float(now),
                    record_id,
                ),
            )
            return True

    def delete(self, record_id: str) -> bool:
        """Delete a memory record."""
        with sqlite3.connect(self.semantic_db) as conn:
            cursor = conn.execute(
                "DELETE FROM semantic_memory WHERE record_id = ?",
                (record_id,),
            )
            return cursor.rowcount > 0

    def search(
        self,
        query: str,
        limit: int = 10,
        category: str | None = None,
        memory_type: str | None = None,
        min_importance: int = 1,
    ) -> MemorySearchResult:
        """Search semantic memory with optional filters."""
        search_term = f"%{query}%"
        params: list[Any] = [search_term, search_term, search_term, search_term]
        where_clauses = ["(content LIKE ? OR category LIKE ? OR memory_type LIKE ? OR key LIKE ?)"]

        if category:
            where_clauses.append("category = ?")
            params.append(category)
        if memory_type:
            where_clauses.append("memory_type = ?")
            params.append(memory_type)
        if min_importance > 1:
            where_clauses.append("importance >= ?")
            params.append(min_importance)

        where_sql = " AND ".join(where_clauses)
        params.append(limit)

        with sqlite3.connect(self.semantic_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT * FROM semantic_memory
                WHERE {where_sql}
                ORDER BY importance DESC, updated_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

        records = []
        for row in rows:
            metadata = _merge_metadata(row["metadata"], {
                "category": row["category"],
                "memory_type": row["memory_type"],
                "importance": row["importance"],
                "confidence": row["confidence"],
                "source": row["source"],
                "evidence": row["evidence"],
            })
            records.append(
                MemoryRecord(
                    key=row["key"],
                    content=row["content"],
                    record_id=row["record_id"],
                    metadata=metadata,
                    created_at=_float_to_dt(row["created_at"]),
                    updated_at=_float_to_dt(row["updated_at"]),
                )
            )

        return MemorySearchResult(query=query, records=tuple(records), total=len(records))

    def clear(self) -> None:
        """Clear all memories (both databases)."""
        with sqlite3.connect(self.semantic_db) as conn:
            conn.execute("DELETE FROM semantic_memory")
        with sqlite3.connect(self.conversation_db) as conn:
            conn.execute("DELETE FROM conversation_logs")

    def metadata(self) -> Mapping[str, Any]:
        """Return store metadata."""
        with sqlite3.connect(self.semantic_db) as conn:
            semantic_count = conn.execute("SELECT COUNT(*) FROM semantic_memory").fetchone()[0]
        with sqlite3.connect(self.conversation_db) as conn:
            conversation_count = conn.execute("SELECT COUNT(*) FROM conversation_logs").fetchone()[0]
        return {
            "conversation_log_count": conversation_count,
            "semantic_memory_count": semantic_count,
            "conversation_db": str(self.conversation_db),
            "semantic_db": str(self.semantic_db),
        }