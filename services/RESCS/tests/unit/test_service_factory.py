"""Service composition tests (factory wiring)."""

from __future__ import annotations

from rescs.config import Settings
from rescs.db.bootstrap import bootstrap_database
from rescs.schemas.record import RecordCreate
from rescs.services.factory import build_services


def make_settings() -> Settings:
    return Settings(
        _env_file=None,
        api_key="test-api-key-0123456789abcdef",
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        storage_dir="rescs_test_storage",
        auto_create_schema=True,
    )


def test_services_from_in_memory_database():
    database = bootstrap_database(make_settings())
    services = build_services(database=database)
    created = services.records.create(
        RecordCreate(namespace="n", key="k", value={"v": 1})
    )
    fetched = services.records.get(created.id)
    assert fetched.value == {"v": 1}
    database.engine.dispose()


def test_services_memory_backend():
    services = build_services(use_memory=True)
    created = services.records.create(
        RecordCreate(namespace="n", key="k", value={"v": 2})
    )
    assert services.records.get(created.id).value == {"v": 2}


def test_services_files_over_persistent_backend(tmp_path):
    from rescs.schemas.file_object import FileObjectCreate

    database = bootstrap_database(make_settings())
    services = build_services(database=database, storage_dir=str(tmp_path / "blobs"))
    uploaded = services.files.create(FileObjectCreate(filename="x.bin"), b"payload")
    meta, content = services.files.download(uploaded.id)
    assert meta.filename == "x.bin"
    assert content == b"payload"
    assert (tmp_path / "blobs" / uploaded.id).is_file()
    database.engine.dispose()
