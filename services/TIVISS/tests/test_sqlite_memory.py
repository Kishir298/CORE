"""Tests for SQLite memory backend."""

import gc
import shutil
import tempfile
from pathlib import Path

import pytest

from tiviss.memory import MemoryKeyError, MemoryRecord, SQLiteMemoryStore


class TestSQLiteMemoryStore:
    """Test SQLite memory store implementation."""

    @pytest.fixture
    def temp_dbs(self):
        """Create temporary database files."""
        tmpdir = tempfile.mkdtemp()
        conv_db = Path(tmpdir) / "conversation_logs.db"
        sem_db = Path(tmpdir) / "semantic_memory.db"
        yield str(conv_db), str(sem_db)
        # Force garbage collection to close any remaining connections
        gc.collect()
        # Clean up with retry for Windows file locking
        for _ in range(3):
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
                break
            except PermissionError:
                import time
                time.sleep(0.1)

    @pytest.fixture
    def store(self, temp_dbs):
        """Create a SQLiteMemoryStore instance."""
        store = SQLiteMemoryStore(temp_dbs[0], temp_dbs[1])
        yield store
        # Explicitly clear to help with connection cleanup
        del store
        gc.collect()

    def test_store_and_retrieve(self, store):
        """Test storing and retrieving a memory record."""
        record = MemoryRecord(key="greeting", content="hello world")
        stored = store.store(record)
        retrieved = store.retrieve(stored.record_id)

        assert retrieved.key == "greeting"
        assert retrieved.content == "hello world"
        assert retrieved.record_id == stored.record_id
        assert retrieved.created_at.tzinfo is not None  # timezone-aware
        assert retrieved.updated_at.tzinfo is not None

    def test_retrieve_missing_raises(self, store):
        """Test that retrieving missing record raises MemoryKeyError."""
        with pytest.raises(MemoryKeyError):
            store.retrieve("non-existent-id")

    def test_update(self, store):
        """Test updating a memory record."""
        record = store.store(MemoryRecord(key="k", content="old"))
        assert store.update(record.record_id, content="new") is True
        retrieved = store.retrieve(record.record_id)
        assert retrieved.content == "new"
        assert retrieved.record_id == record.record_id
        assert retrieved.updated_at >= record.updated_at

    def test_update_missing_returns_false(self, store):
        """Test that updating missing record returns False."""
        assert store.update("non-existent-id", content="x") is False

    def test_delete(self, store):
        """Test deleting a memory record."""
        record = store.store(MemoryRecord(key="k", content="v"))
        assert store.delete(record.record_id) is True
        with pytest.raises(MemoryKeyError):
            store.retrieve(record.record_id)

    def test_delete_missing_returns_false(self, store):
        """Test that deleting missing record returns False."""
        assert store.delete("non-existent-id") is False

    def test_search(self, store):
        """Test searching memory records."""
        store.store(MemoryRecord(key="alpha", content="hello world"))
        store.store(MemoryRecord(key="beta", content="goodbye world"))
        store.store(MemoryRecord(key="gamma", content="nothing"))

        result = store.search("world")
        assert result.total == 2
        assert {r.key for r in result.records} == {"alpha", "beta"}

        result = store.search("hello")
        assert result.total == 1
        assert result.records[0].key == "alpha"

    def test_search_with_category_filter(self, store):
        """Test searching with category filter."""
        store.store(MemoryRecord(key="a1", content="test", metadata={"category": "personal"}))
        store.store(MemoryRecord(key="a2", content="test", metadata={"category": "work"}))

        result = store.search("test", category="personal")
        assert result.total == 1
        assert result.records[0].key == "a1"
        assert result.records[0].metadata.get("category") == "personal"

    def test_search_with_importance_filter(self, store):
        """Test searching with minimum importance filter."""
        store.store(MemoryRecord(key="low", content="test", metadata={"importance": 1}))
        store.store(MemoryRecord(key="high", content="test", metadata={"importance": 10}))

        result = store.search("test", min_importance=5)
        assert result.total == 1
        assert result.records[0].key == "high"

    def test_clear(self, store):
        """Test clearing all memories."""
        store.store(MemoryRecord(key="a", content="1"))
        store.store(MemoryRecord(key="b", content="2"))
        store.clear()
        meta = store.metadata()
        assert meta["semantic_memory_count"] == 0
        assert meta["conversation_log_count"] == 0

    def test_metadata(self, store):
        """Test metadata statistics."""
        store.store(MemoryRecord(key="a", content="1"))
        store.store(MemoryRecord(key="b", content="2"))
        meta = store.metadata()
        assert meta["semantic_memory_count"] == 2
        assert meta["conversation_log_count"] == 0
        assert "semantic_db" in meta
        assert "conversation_db" in meta

    def test_timezone_aware_datetimes(self, store):
        """Test that datetimes are timezone-aware (not floats)."""
        record = store.store(MemoryRecord(key="test", content="content"))
        retrieved = store.retrieve(record.record_id)

        # Should be datetime objects with timezone info
        assert retrieved.created_at.tzinfo is not None
        assert retrieved.updated_at.tzinfo is not None
        # Should not be float timestamps
        assert not isinstance(retrieved.created_at, float)
        assert not isinstance(retrieved.updated_at, float)

    def test_preserves_original_key(self, store):
        """Test that original key is preserved (not replaced with record_id)."""
        record = store.store(MemoryRecord(key="my_custom_key", content="content"))
        retrieved = store.retrieve(record.record_id)
        assert retrieved.key == "my_custom_key"
        assert retrieved.key != record.record_id

    def test_metadata_columns_updated_atomically(self, store):
        """Test that metadata columns (category, importance, source) are updated atomically."""
        record = store.store(MemoryRecord(
            key="test",
            content="content",
            metadata={"category": "old_cat", "importance": 3, "source": "old_src"}
        ))

        # Update with new metadata
        store.update(record.record_id, metadata={
            "category": "new_cat",
            "importance": 8,
            "source": "new_src"
        })

        retrieved = store.retrieve(record.record_id)
        assert retrieved.metadata.get("category") == "new_cat"
        assert retrieved.metadata.get("importance") == 8
        assert retrieved.metadata.get("source") == "new_src"

    def test_conversation_log(self, store):
        """Test conversation log functionality."""
        log_id = store.append_conversation(
            request_id="req-1",
            request_content="Hello",
            response_content="Hi there!",
            metadata={"session": "test"}
        )
        assert log_id > 0

        history = store.get_conversation_history(limit=10)
        assert len(history) == 1
        assert history[0].request_id == "req-1"
        assert history[0].request_content == "Hello"
        assert history[0].response_content == "Hi there!"
        assert history[0].metadata == {"session": "test"}
        assert history[0].created_at.tzinfo is not None  # timezone-aware

    def test_export_import_roundtrip(self, temp_dbs):
        """Test export/import roundtrip with SQLite backend."""
        from tiviss.configuration import TIVISSConfig
        from tiviss.identity import Ownership
        from tiviss.state_io import EXPORT_MARKER, export_state, import_state

        store = SQLiteMemoryStore(temp_dbs[0], temp_dbs[1])

        # Store some records
        store.store(MemoryRecord(key="fact1", content="likes tea", metadata={"category": "preference"}))
        store.store(MemoryRecord(key="fact2", content="dislikes coffee", metadata={"category": "preference"}))

        records = store.search("").records

        config = TIVISSConfig.load({
            "agent": {"name": "t", "owner_id": "kishir", "agent_id": "a-1"},
            "permissions": {"allow": ["conversation.generate"]},
        })
        identity = config.build_identity()
        ownership = Ownership.create("kishir")

        doc = export_state(
            identity=identity,
            ownership=ownership,
            model={"provider_id": "mock", "model_id": "m"},
            permissions={"allow": ["conversation.generate"], "deny": []},
            memory_records=records,
            counters={"requests_handled": 3},
        )

        assert doc[EXPORT_MARKER] is True
        assert doc["version"] == 1
        assert doc["integrity"]

        # Import and verify
        restored = import_state(doc)
        assert restored.agent_id == "a-1"
        assert restored.identity.owner_id == "kishir"
        assert restored.ownership.owner_id == "kishir"
        assert len(restored.memory_records) == 2
        assert restored.counters == {"requests_handled": 3}

        # Verify memory records have correct keys and content
        keys = {r.key for r in restored.memory_records}
        assert keys == {"fact1", "fact2"}

    def test_migration_adds_key_column(self, temp_dbs):
        """Test that migration adds key column for older databases."""
        # Create an old-style database without key column
        import sqlite3
        conv_db, sem_db = temp_dbs

        # Create old schema (without key column)
        with sqlite3.connect(sem_db) as conn:
            conn.execute("""
                CREATE TABLE semantic_memory (
                    record_id TEXT PRIMARY KEY,
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
            # Insert a record
            conn.execute("""
                INSERT INTO semantic_memory 
                (record_id, content, category, memory_type, importance, confidence, source, evidence, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("old-record-1", "old content", "general", "fact", 5, 0.7, "user-stated", "", "{}", 1234567890.0, 1234567890.0))

        # Now initialize the store - should migrate
        store = SQLiteMemoryStore(conv_db, sem_db)

        # Should be able to retrieve the old record
        retrieved = store.retrieve("old-record-1")
        assert retrieved.content == "old content"
        # Key should default to record_id for migrated records
        assert retrieved.key == "old-record-1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
