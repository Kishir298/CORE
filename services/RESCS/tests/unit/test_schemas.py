"""Pydantic schema validation tests."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from rescs.domain import RecordData
from rescs.schemas.file_object import (
    DEFAULT_MIME_TYPE,
    FileObjectCreate,
    FileObjectRead,
)
from rescs.schemas.record import RecordCreate, RecordRead, RecordUpdate


def test_record_create_valid():
    schema = RecordCreate(
        key="profile", value={"name": "x"}, metadata={"tier": 2}
    )
    assert schema.namespace == "default"
    assert schema.owner == "system"
    assert schema.idempotency_key is None


def test_record_create_rejects_empty_key():
    with pytest.raises(ValidationError):
        RecordCreate(key="", value={})


def test_record_create_rejects_non_json_value():
    with pytest.raises(ValidationError):
        RecordCreate(key="k", value={"when": datetime(2026, 1, 1)})


def test_record_create_rejects_bad_namespace():
    with pytest.raises(ValidationError):
        RecordCreate(key="k", value={}, namespace="has space")


def test_record_update_partial():
    schema = RecordUpdate(value={"new": 1})
    assert schema.value == {"new": 1}
    assert schema.metadata is None
    assert schema.key is None


def test_record_read_from_domain():
    record = RecordData(
        id="r1",
        namespace="default",
        key="k",
        value={"a": 1},
        metadata={"m": 2},
        owner="alice",
        version=2,
        etag="e",
    )
    schema = RecordRead.from_domain(record)
    payload = schema.model_dump(mode="json")
    assert payload["id"] == "r1"
    assert payload["version"] == 2
    assert payload["etag"] == "e"
    assert "updated_at" in payload


def test_file_create_defaults():
    schema = FileObjectCreate(filename="a.bin")
    assert schema.mime_type == DEFAULT_MIME_TYPE
    assert schema.metadata == {}
    assert schema.owner == "system"


def test_file_create_rejects_non_json_metadata():
    with pytest.raises(ValidationError):
        FileObjectCreate(filename="a.bin", metadata={"when": datetime(2026, 1, 1)})


def test_file_read_from_domain():
    from rescs.domain import FileObjectData

    file_obj = FileObjectData(
        id="f1",
        filename="n.txt",
        mime_type="text/plain",
        size=7,
        storage_path="obj/n.txt",
        sha256="a" * 64,
    )
    schema = FileObjectRead.from_domain(file_obj)
    assert schema.sha256 == "a" * 64
    assert schema.filename == "n.txt"
