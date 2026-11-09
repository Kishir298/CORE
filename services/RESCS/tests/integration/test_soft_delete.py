"""Integration: soft delete, restore, and purge (Phase 14).

DELETE tombstones resources (metadata preserved, hidden from ordinary
reads/lists); POST .../restore recovers; DELETE .../purge removes forever.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from rescs.config import Settings
from rescs.main import create_app

API_KEY = "test-api-key-0123456789abcdef"
RECORDS = "/api/v1/records"
FILES = "/api/v1/files"


def test_record_soft_delete_hides_but_preserves(client: TestClient):
    created = client.post(
        RECORDS, json={"namespace": "sd", "key": "doc", "value": {"v": 1}}
    ).json()
    record_id = created["id"]

    assert client.delete(f"{RECORDS}/{record_id}").status_code == 204
    # Ordinary reads behave as if the resource is gone.
    assert client.get(f"{RECORDS}/{record_id}").status_code == 404
    assert client.get(f"{RECORDS}?namespace=sd").json()["total"] == 0
    # ... but the tombstone is recoverable through the admin surface.
    deleted = client.get(f"{RECORDS}?namespace=sd&include_deleted=true").json()
    assert deleted["total"] == 1
    assert deleted["items"][0]["deleted_at"] is not None
    assert deleted["items"][0]["version"] == 2
    admin = client.get("/api/v1/admin/records/deleted?namespace=sd").json()
    assert admin["total"] == 1


def test_record_restore_and_purge(client: TestClient):
    created = client.post(
        RECORDS, json={"namespace": "sd", "key": "doomed", "value": {}}
    ).json()
    record_id = created["id"]
    client.delete(f"{RECORDS}/{record_id}")

    restored = client.post(f"{RECORDS}/{record_id}/restore")
    assert restored.status_code == 200, restored.text
    body = restored.json()
    assert body["deleted_at"] is None
    assert body["version"] == 3
    assert client.get(f"{RECORDS}/{record_id}").status_code == 200

    # Restoring a live record is a clean 400, not a silent no-op.
    again = client.post(f"{RECORDS}/{record_id}/restore")
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "INVALID_REQUEST"

    assert client.delete(f"{RECORDS}/{record_id}/purge").status_code == 204
    assert client.get(f"{RECORDS}/{record_id}").status_code == 404
    assert (
        client.get(f"{RECORDS}?namespace=sd&include_deleted=true").json()["total"]
        == 0
    )
    assert client.delete(f"{RECORDS}/{record_id}/purge").status_code == 404


def test_record_restore_conflicts_with_live_key(client: TestClient):
    first = client.post(
        RECORDS, json={"namespace": "sd", "key": "reused", "value": {"gen": 1}}
    ).json()
    client.delete(f"{RECORDS}/{first['id']}")
    # The freed key can be reused while the tombstone exists (live-only uniqueness).
    second = client.post(
        RECORDS, json={"namespace": "sd", "key": "reused", "value": {"gen": 2}}
    )
    assert second.status_code == 201
    # Restoring the tombstone now collides with the live occupant.
    conflict = client.post(f"{RECORDS}/{first['id']}/restore")
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "CONFLICT"


def test_record_delete_restore_purge_honor_if_match(client: TestClient):
    created = client.post(
        RECORDS, json={"namespace": "sd", "key": "guarded", "value": {}}
    ).json()
    record_id = created["id"]
    assert (
        client.delete(f"{RECORDS}/{record_id}", headers={"If-Match": "stale"}).status_code
        == 412
    )
    assert client.delete(
        f"{RECORDS}/{record_id}", headers={"If-Match": created["etag"]}
    ).status_code == 204
    assert (
        client.post(
            f"{RECORDS}/{record_id}/restore", headers={"If-Match": "stale"}
        ).status_code
        == 412
    )
    assert (
        client.post(
            f"{RECORDS}/{record_id}/restore",
            headers={"If-Match": created["etag"]},
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"{RECORDS}/{record_id}/purge", headers={"If-Match": "wrong"}
        ).status_code
        == 412
    )
    assert client.delete(
        f"{RECORDS}/{record_id}/purge", headers={"If-Match": created["etag"]}
    ).status_code == 204


def test_file_soft_delete_keeps_blob_and_restores(client: TestClient):
    data = b"restore-me-bytes"
    uploaded = client.post(
        FILES, files={"upload": ("r.bin", data, "application/octet-stream")}
    ).json()
    file_id = uploaded["id"]

    assert client.delete(f"{FILES}/{file_id}").status_code == 204
    assert client.get(f"{FILES}/{file_id}").status_code == 404
    assert client.get(f"{FILES}/{file_id}/content").status_code == 404
    assert client.get(f"{FILES}?include_deleted=true").json()["total"] == 1

    restored = client.post(f"{FILES}/{file_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["deleted_at"] is None
    download = client.get(f"{FILES}/{file_id}/content")
    assert download.status_code == 200
    assert download.content == data

    assert client.delete(f"{FILES}/{file_id}/purge").status_code == 204
    assert client.get(f"{FILES}/{file_id}").status_code == 404
    store = client.app.state.services.files.object_store
    assert store.exists(file_id) is False


def test_tombstones_survive_restart(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        api_key=API_KEY,
        database_url=f"sqlite:///{tmp_path}/rescs.db",
        storage_dir=str(tmp_path / "blobs"),
        environment="test",
    )
    with TestClient(
        create_app(settings=settings), headers={"X-API-Key": API_KEY}
    ) as first:
        created = first.post(
            RECORDS, json={"namespace": "sd", "key": "persist", "value": {}}
        ).json()
        assert first.delete(f"{RECORDS}/{created['id']}").status_code == 204

    with TestClient(
        create_app(settings=settings), headers={"X-API-Key": API_KEY}
    ) as second:
        assert second.get(f"{RECORDS}/{created['id']}").status_code == 404
        restored = second.post(f"{RECORDS}/{created['id']}/restore")
        assert restored.status_code == 200
        assert second.get(f"{RECORDS}/{created['id']}").status_code == 200


def test_scoped_owner_cannot_restore_others(scoped_client: TestClient):
    from tests.conftest import SCOPED_OWNER

    created = scoped_client.post(
        RECORDS,
        json={"namespace": "sd", "key": "mine", "value": {}, "owner": SCOPED_OWNER},
    ).json()
    assert scoped_client.delete(f"{RECORDS}/{created['id']}").status_code == 204
    # Another owner filter is rejected even on the deleted listing.
    rejected = scoped_client.get("/api/v1/admin/records/deleted?owner=someone-else")
    assert rejected.status_code == 401
    # Own tombstone restores fine under the lock.
    assert scoped_client.post(f"{RECORDS}/{created['id']}/restore").status_code == 200

