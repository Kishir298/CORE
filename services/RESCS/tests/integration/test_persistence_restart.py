"""Integration: persistence and restart behavior on file-backed SQLite.

Proves §8.3 — data committed through the real SQLAlchemy backend +
LocalObjectStore survives application restart (engine dispose + rebuild
on the same database file and storage directory).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from rescs.config import Settings
from rescs.main import create_app

API_KEY = "test-api-key-0123456789abcdef"
RECORDS = "/api/v1/records"
FILES = "/api/v1/files"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        api_key=API_KEY,
        api_key_owner="",
        database_url=f"sqlite:///{tmp_path}/rescs_restart.db",
        storage_dir=str(tmp_path / "blobs"),
        environment="test",
    )


def test_records_survive_restart(tmp_path: Path):
    settings = _settings(tmp_path)
    payload = {
        "namespace": "core.ops.runnables",
        "key": "runnable-1",
        "value": {"state": "queued", "outputs": []},
        "metadata": {"neighbor_links": ["a"]},
        "owner": "owner-A",
    }
    with TestClient(
        create_app(settings=settings), headers={"X-API-Key": API_KEY}
    ) as first:
        created = first.post(RECORDS, json=payload)
        assert created.status_code == 201, created.text
        record = created.json()
        record_id = record["id"]
        assert record["version"] == 1
        assert record["etag"]
        assert record["created_at"] and record["updated_at"]

    # New application instance over the same files (simulated restart).
    with TestClient(
        create_app(settings=settings), headers={"X-API-Key": API_KEY}
    ) as second:
        assert second.get("/health/ready").status_code == 200
        reread = second.get(f"{RECORDS}/{record_id}")
        assert reread.status_code == 200, reread.text
        body = reread.json()
        assert body["id"] == record_id
        assert body["namespace"] == "core.ops.runnables"
        assert body["value"] == {"state": "queued", "outputs": []}
        assert body["metadata"] == {"neighbor_links": ["a"]}
        assert body["owner"] == "owner-A"
        assert body["version"] == 1
        assert body["etag"] == record["etag"]
        assert body["created_at"] == record["created_at"]
        # Writes still work after restart and bump version deterministically.
        patched = second.patch(
            f"{RECORDS}/{record_id}",
            json={"value": {"state": "running", "outputs": []}},
        )
        assert patched.status_code == 200
        assert patched.json()["version"] == 2
        assert patched.json()["etag"] != record["etag"]


def test_files_survive_restart_with_integrity(tmp_path: Path):
    settings = _settings(tmp_path)
    data = b"restart-persistent-bytes-" * 64
    digest = hashlib.sha256(data).hexdigest()
    with TestClient(
        create_app(settings=settings), headers={"X-API-Key": API_KEY}
    ) as first:
        upload = first.post(
            FILES,
            files={"upload": ("artifact.bin", data, "application/octet-stream")},
            data={"owner": "owner-B"},
        )
        assert upload.status_code == 201, upload.text
        meta = upload.json()
        file_id = meta["id"]
        assert meta["sha256"] == digest
        assert meta["size"] == len(data)
        assert meta["owner"] == "owner-B"
        # Blob really landed on disk (not only in the database row).
        assert any((tmp_path / "blobs").iterdir())

    with TestClient(
        create_app(settings=settings), headers={"X-API-Key": API_KEY}
    ) as second:
        reread = second.get(f"{FILES}/{file_id}")
        assert reread.status_code == 200, reread.text
        assert reread.json()["sha256"] == digest
        assert reread.json()["version"] == 1
        download = second.get(f"{FILES}/{file_id}/content")
        assert download.status_code == 200
        assert download.content == data
        assert download.headers["x-file-sha256"] == digest
        assert download.headers["x-file-size"] == str(len(data))
        assert download.headers["etag"]

