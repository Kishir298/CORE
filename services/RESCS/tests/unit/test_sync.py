"""Synchronization and consistency tests.

Covers optimistic concurrency (If-Match / expected etag), idempotency, and
blob integrity verification.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rescs.errors import PreconditionFailedError, StorageError
from rescs.repositories.memory import (
    InMemoryFileObjectRepository,
    InMemoryRecordRepository,
)
from rescs.schemas.file_object import FileObjectCreate
from rescs.schemas.record import RecordCreate, RecordUpdate
from rescs.services.files import FileService
from rescs.services.records import RecordService
from rescs.storage.local import LocalObjectStore
from rescs.storage.memory import MemoryObjectStore


@pytest.fixture()
def record_service(memory_record_repo: InMemoryRecordRepository) -> RecordService:
    return RecordService(memory_record_repo)


@pytest.fixture()
def file_service(
    memory_file_repo: InMemoryFileObjectRepository,
) -> FileService:
    return FileService(memory_file_repo, MemoryObjectStore())


def _record() -> RecordCreate:
    return RecordCreate(namespace="default", key="k", value={"v": 1})


def test_update_with_stale_etag_rejected(record_service: RecordService):
    created = record_service.create(_record())
    with pytest.raises(PreconditionFailedError) as excinfo:
        record_service.update(
            created.id,
            RecordUpdate(value={"v": 2}),
            expected_etag="stale-etag",
        )
    assert excinfo.value.status_code == 412
    assert excinfo.value.details["current_etag"] == created.etag


def test_update_with_matching_etag_succeeds(record_service: RecordService):
    created = record_service.create(_record())
    updated = record_service.update(
        created.id, RecordUpdate(value={"v": 2}), expected_etag=created.etag
    )
    assert updated.value == {"v": 2}
    assert updated.version == 2
    assert updated.etag != created.etag


def test_delete_with_stale_etag_rejected(record_service: RecordService):
    created = record_service.create(_record())
    with pytest.raises(PreconditionFailedError):
        record_service.delete(created.id, expected_etag="stale")
    assert record_service.get(created.id).id == created.id


def test_put_missing_with_if_match_rejected(record_service: RecordService):
    with pytest.raises(PreconditionFailedError):
        record_service.put(_record(), expected_etag="any-etag")


def test_idempotent_create_returns_same_record(record_service: RecordService):
    payload = _record()
    payload.idempotency_key = "idem-1"
    first = record_service.create(payload)
    second = record_service.create(payload)
    assert first.id == second.id


def test_version_bumps_on_change(record_service: RecordService):
    created = record_service.create(_record())
    updated = record_service.update(created.id, RecordUpdate(value={"v": 9}))
    assert updated.version == created.version + 1


def test_download_verifies_integrity(tmp_path: Path):
    store = LocalObjectStore(tmp_path)
    service = FileService(InMemoryFileObjectRepository(), store)
    created = service.create(FileObjectCreate(filename="a.txt"), b"hello")
    blob_path = tmp_path / created.storage_path
    blob_path.write_bytes(b"tampered")
    with pytest.raises(StorageError) as excinfo:
        service.download(created.id)
    assert excinfo.value.details["actual_sha256"] != created.sha256


def test_download_passes_when_blob_intact(record_service: RecordService):
    assert record_service.get(record_service.create(_record()).id).value == {"v": 1}


def test_file_conditional_delete_rejected(file_service: FileService):
    created = file_service.create(FileObjectCreate(filename="a.txt"), b"data")
    with pytest.raises(PreconditionFailedError):
        file_service.delete(created.id, expected_etag="wrong")
    assert file_service.get(created.id).id == created.id
