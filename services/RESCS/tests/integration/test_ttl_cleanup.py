"""Integration: TTL expiration and explicit cleanup (Phase 15).

Expired resources behave as absent for ordinary operations; the admin
cleanup endpoint purges them deterministically (dry-run supported).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from rescs.config import Settings
from rescs.main import create_app

API_KEY = "test-api-key-0123456789abcdef"
RECORDS = "/api/v1/records"
FILES = "/api/v1/files"
CLEANUP = "/api/v1/admin/cleanup"


def _future(hours: int = 1) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()


def test_expired_record_behaves_as_absent(client: TestClient):
    created = client.post(
        RECORDS,
        json={"namespace": "ttl", "key": "soon-gone", "value": {}, "expires_at": _future()},
    ).json()
    assert created["expires_at"] is not None

    # Force expiry by patching the timestamp into the past.
    services = client.app.state.services
    row = services.records._repo.get_including_deleted(created["id"])
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    services.records._repo.update(row)

    assert client.get(f"{RECORDS}/{created['id']}").status_code == 404
    assert client.get(f"{RECORDS}?namespace=ttl").json()["total"] == 0
    assert client.get(f"{RECORDS}?namespace=ttl&query=soon").json()["total"] == 0
    # ... but still visible with the explicit expired flag (same owner scope).
    flagged = client.get(f"{RECORDS}?namespace=ttl&include_expired=true").json()
    assert flagged["total"] == 1


def test_past_expiry_rejected(client: TestClient):
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    response = client.post(
        RECORDS,
        json={"namespace": "ttl", "key": "already-dead", "value": {}, "expires_at": past},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_cleanup_dry_run_then_purge(client: TestClient):
    services = client.app.state.services
    created = client.post(
        RECORDS,
        json={"namespace": "ttl", "key": "cleanup-me", "value": {}, "expires_at": _future()},
    ).json()
    row = services.records._repo.get_including_deleted(created["id"])
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    services.records._repo.update(row)

    uploaded = client.post(
        FILES,
        files={"upload": ("e.bin", b"expiring", "application/octet-stream")},
        data={"expires_at": _future()},
    )
    assert uploaded.status_code == 201, uploaded.text
    file_row = services.files._repo.get_including_deleted(uploaded.json()["id"])
    file_row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    services.files._repo.update(file_row)

    dry = client.post(CLEANUP, json={"dry_run": True, "batch": 500}).json()
    assert dry["dry_run"] is True
    assert dry["records_purged"] == 1
    assert dry["files_purged"] == 1
    # Dry run changes nothing.
    assert client.get(f"{RECORDS}?namespace=ttl&include_expired=true").json()["total"] == 1

    real = client.post(CLEANUP, json={"dry_run": False, "batch": 500}).json()
    assert real["records_purged"] == 1
    assert real["files_purged"] == 1
    assert client.get(f"{RECORDS}?namespace=ttl&include_expired=true").json()["total"] == 0
    # File blob was reclaimed too.
    assert services.files.object_store.exists(uploaded.json()["id"]) is False


def test_expired_occupant_reclaimed_on_write(client: TestClient):
    services = client.app.state.services
    created = client.post(
        RECORDS,
        json={"namespace": "ttl", "key": "reclaimed", "value": {"gen": 1}, "expires_at": _future()},
    ).json()
    row = services.records._repo.get_including_deleted(created["id"])
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    services.records._repo.update(row)

    # A fresh PUT transparently replaces the expired occupant (no 409).
    replaced = client.put(
        RECORDS,
        json={"namespace": "ttl", "key": "reclaimed", "value": {"gen": 2}},
    )
    assert replaced.status_code == 200
    assert replaced.json()["value"] == {"gen": 2}
    assert replaced.json()["id"] != created["id"]


def test_expiry_survives_restart(tmp_path: Path):
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
            RECORDS,
            json={"namespace": "ttl", "key": "persist", "value": {}, "expires_at": _future()},
        ).json()
        assert created["expires_at"] is not None

    with TestClient(
        create_app(settings=settings), headers={"X-API-Key": API_KEY}
    ) as second:
        reread = second.get(f"{RECORDS}/{created['id']}").json()
        assert reread["expires_at"] == created["expires_at"]


def test_cleanup_requires_auth(settings):
    from rescs.main import create_app as _create

    app = _create(settings=settings)
    with TestClient(app) as anon:
        assert anon.post(CLEANUP, json={}).status_code == 401
        assert anon.get("/api/v1/admin/audit").status_code == 401

