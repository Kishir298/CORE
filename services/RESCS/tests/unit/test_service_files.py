"""File service behaviour tests."""

from __future__ import annotations

import pytest

from rescs.errors import NotFoundError, StorageError
from rescs.repositories.memory import InMemoryFileObjectRepository
from rescs.schemas.file_object import FileObjectCreate
from rescs.services.files import FileService
from rescs.storage.memory import MemoryObjectStore


@pytest.fixture()
def service():
    return FileService(InMemoryFileObjectRepository(), MemoryObjectStore())


def make_payload(**overrides) -> FileObjectCreate:
    values = dict(filename="a.txt", mime_type="text/plain")
    values.update(overrides)
    return FileObjectCreate(**values)


def test_create_fingerprints_payload(service):
    data = b"hello world"
    created = service.create(make_payload(), data)
    assert created.size == len(data)
    assert created.sha256 == (
        "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
    )
    assert created.etag
    assert created.version == 1
    assert created.storage_path == created.id


def test_download_round_trip(service):
    data = b"file-bytes"
    created = service.create(make_payload(filename="f.bin"), data)
    fetched, content = service.download(created.id)
    assert fetched.id == created.id
    assert content == data


def test_get_metadata(service):
    created = service.create(make_payload(filename="n.txt"), b"x")
    fetched = service.get(created.id)
    assert fetched.filename == "n.txt"
    assert fetched.mime_type == "text/plain"


def test_missing_file(service):
    with pytest.raises(NotFoundError):
        service.get("missing")
    with pytest.raises(NotFoundError):
        service.download("missing")


def test_metadata_without_blob_raises_storage_error(service):
    created = service.create(make_payload(), b"data")
    service._store.delete(created.storage_path)
    with pytest.raises(StorageError):
        service.download(created.id)


def test_delete_soft_deletes_and_keeps_blob_for_restore(service):
    created = service.create(make_payload(), b"x")
    service.delete(created.id)
    with pytest.raises(NotFoundError):
        service.get(created.id)
    # Soft delete retains the blob so restore is instant.
    assert service._store.exists(created.id)
    tombstone = service.get_including_deleted(created.id)
    assert tombstone.deleted_at is not None
    restored = service.restore(created.id)
    assert restored.deleted_at is None
    assert service.get(created.id).id == created.id


def test_purge_removes_metadata_and_blob(service):
    created = service.create(make_payload(), b"x")
    service.purge(created.id)
    with pytest.raises(NotFoundError):
        service.get_including_deleted(created.id)
    assert not service._store.exists(created.id)


def test_delete_missing_raises(service):
    with pytest.raises(NotFoundError):
        service.delete("missing")


def test_idempotent_create(service):
    payload = make_payload(idempotency_key="up-1")
    first = service.create(payload, b"data")
    second = service.create(payload, b"data")
    assert first.id == second.id


def test_same_idempotency_key_returns_existing(service):
    first = service.create(make_payload(idempotency_key="up-2"), b"data")
    second = service.create(
        make_payload(idempotency_key="up-2", filename="other.txt"), b"other"
    )
    assert second.id == first.id
    assert second.filename == "a.txt"


def test_list(service):
    service.create(make_payload(filename="a.txt"), b"a")
    service.create(make_payload(filename="b.txt"), b"b")
    page = service.list(limit=10)
    assert page.total == 2
    assert {item.filename for item in page.items} == {"a.txt", "b.txt"}


def test_list_empty(service):
    page = service.list()
    assert page.total == 0
    assert page.items == []

def test_download_stream_verifies_integrity(service):
    created = service.create(make_payload(filename='s.bin'), b'stream-bytes')
    meta, stream = service.download_stream(created.id)
    assert meta.id == created.id
    assert b''.join(stream) == b'stream-bytes'


def test_download_stream_tampered_blob_raises(service):
    created = service.create(make_payload(filename='t.bin'), b'good-bytes')
    # Tamper the blob behind the metadata: stream must abort, not 200 bad bytes.
    service._store.put(created.storage_path, b'evil-bytes!')
    meta, stream = service.download_stream(created.id)
    with pytest.raises(StorageError, match='integrity'):
        b''.join(stream)


def test_download_stream_abandon_does_not_raise(service):
    created = service.create(make_payload(filename='a.bin'), b'abandon-bytes')
    meta, stream = service.download_stream(created.id)
    assert next(stream) is not None
    stream.close()

