"""Domain object tests."""

from __future__ import annotations

from datetime import UTC, datetime

from rescs.domain import FileObjectData, RecordData, ensure_utc, utcnow


def test_utcnow_is_aware():
    assert utcnow().tzinfo is not None


def test_ensure_utc_preserves_aware():
    value = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert ensure_utc(value) == value


def test_ensure_utc_naive_assumed_utc():
    naive = datetime(2026, 1, 1, 12, 0)
    assert ensure_utc(naive).tzinfo is not None


def test_ensure_utc_none():
    assert ensure_utc(None) is None


def test_record_to_dict_round_trip():
    record = RecordData(
        id="rec-1",
        namespace="default",
        key="profile",
        value={"name": "x"},
        metadata={"a": 1},
        owner="alice",
        version=3,
        idempotency_key="idem-1",
        etag="abcdef",
    )
    payload = record.to_dict()
    assert payload["id"] == "rec-1"
    assert payload["value"] == {"name": "x"}
    assert payload["metadata"] == {"a": 1}
    assert payload["owner"] == "alice"
    assert payload["version"] == 3
    assert payload["idempotency_key"] == "idem-1"
    assert payload["etag"] == "abcdef"
    assert payload["created_at"].tzinfo is not None


def test_record_defaults():
    record = RecordData(id="r", namespace="default", key="k", value={})
    assert record.owner == "system"
    assert record.version == 1
    assert record.idempotency_key is None
    assert record.etag == ""
    assert record.metadata == {}


def test_file_object_to_dict():
    file_obj = FileObjectData(
        id="f-1",
        filename="a.txt",
        mime_type="text/plain",
        size=10,
        storage_path="obj/a.txt",
        sha256="abc",
    )
    payload = file_obj.to_dict()
    assert payload["filename"] == "a.txt"
    assert payload["size"] == 10
    assert payload["mime_type"] == "text/plain"
    assert payload["version"] == 1
