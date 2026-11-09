"""Integration: bulk operations and resource governance (Phases 20–21)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from rescs.config import Settings
from rescs.main import create_app

API_KEY = "test-api-key-0123456789abcdef"
RECORDS = "/api/v1/records"
FILES = "/api/v1/files"
BULK = "/api/v1/records/bulk"


def _custom_app(tmp_path: Path, **overrides) -> TestClient:
    settings = Settings(
        _env_file=None,
        api_key=API_KEY,
        database_url="sqlite+pysqlite:///:memory:",
        storage_dir=str(tmp_path / "blobs"),
        environment="test",
        **overrides,
    )
    app = create_app(settings=settings)
    return TestClient(app, headers={"X-API-Key": API_KEY})


def test_bulk_mixed_operations(client: TestClient):
    response = client.post(
        BULK,
        json={
            "operations": [
                {"op": "create", "record": {"namespace": "bk", "key": "a", "value": {"n": 1}}},
                {"op": "create", "record": {"namespace": "bk", "key": "b", "value": {"n": 2}}},
            ]
        },
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert [r["status"] for r in results] == ["created", "created"]
    id_a = results[0]["id"]

    mixed = client.post(
        BULK,
        json={
            "operations": [
                {"op": "put", "record": {"namespace": "bk", "key": "a", "value": {"n": 10}}},
                {"op": "delete", "id": id_a},
                {"op": "delete", "id": "no-such-id"},
                {"op": "frobnicate", "id": id_a},
            ]
        },
    ).json()["results"]
    assert mixed[0]["status"] == "put" and mixed[0]["id"] == id_a
    assert mixed[1]["status"] == "deleted"
    assert mixed[2]["status"] == "error" and mixed[2]["code"] == "NOT_FOUND"
    assert mixed[3]["status"] == "error" and mixed[3]["code"] == "INVALID_REQUEST"
    # Partial failure is explicit: the put and delete both applied.
    assert client.get(f"{RECORDS}/{id_a}").status_code == 404


def test_bulk_batch_bound(tmp_path: Path):
    with _custom_app(tmp_path, max_bulk_batch=2) as app:
        oversized = app.post(
            BULK,
            json={
                "operations": [
                    {"op": "create", "record": {"namespace": "bk", "key": f"k{i}", "value": {}}}
                    for i in range(3)
                ]
            },
        )
        assert oversized.status_code == 400
        assert oversized.json()["error"]["code"] == "INVALID_REQUEST"


def test_bulk_restore_and_purge(client: TestClient):
    created = client.post(
        BULK,
        json={"operations": [{"op": "create", "record": {"namespace": "bk", "key": "z", "value": {}}}]},
    ).json()["results"][0]
    record_id = created["id"]
    client.delete(f"{RECORDS}/{record_id}")
    results = client.post(
        BULK,
        json={
            "operations": [
                {"op": "restore", "id": record_id},
                {"op": "purge", "id": record_id},
            ]
        },
    ).json()["results"]
    assert [r["status"] for r in results] == ["restored", "purged"]
    assert client.get(f"{RECORDS}/{record_id}").status_code == 404


def test_record_count_quota(tmp_path: Path):
    with _custom_app(tmp_path, max_records_per_owner=2) as app:
        for key in ("q1", "q2"):
            response = app.post(
                RECORDS,
                json={"namespace": "quota", "key": key, "value": {}, "owner": "owner-Q"},
            )
            assert response.status_code == 201
        over = app.post(
            RECORDS,
            json={"namespace": "quota", "key": "q3", "value": {}, "owner": "owner-Q"},
        )
        assert over.status_code == 403
        assert over.json()["error"]["code"] == "QUOTA_EXCEEDED"
        # A different owner is unaffected.
        assert (
            app.post(
                RECORDS,
                json={"namespace": "quota", "key": "other", "value": {}, "owner": "owner-R"},
            ).status_code
            == 201
        )
        # Soft-deleted resources stop consuming quota.
        first = app.get(f"{RECORDS}?namespace=quota&owner=owner-Q").json()["items"][0]
        assert app.delete(f"{RECORDS}/{first['id']}").status_code == 204
        retry = app.post(
            RECORDS,
            json={"namespace": "quota", "key": "q3", "value": {}, "owner": "owner-Q"},
        )
        assert retry.status_code == 201


def test_file_count_and_byte_quotas(tmp_path: Path):
    with _custom_app(tmp_path, max_files_per_owner=1, max_bytes_per_owner=64) as app:
        first = app.post(
            FILES,
            files={"upload": ("a.bin", b"a" * 32, "application/octet-stream")},
            data={"owner": "owner-Q"},
        )
        assert first.status_code == 201
        # Second file trips the count quota even though bytes would fit.
        second = app.post(
            FILES,
            files={"upload": ("b.bin", b"b" * 8, "application/octet-stream")},
            data={"owner": "owner-Q"},
        )
        assert second.status_code == 403
        assert second.json()["error"]["code"] == "QUOTA_EXCEEDED"

    with _custom_app(tmp_path, max_bytes_per_owner=40) as app:
        assert (
            app.post(
                FILES,
                files={"upload": ("a.bin", b"a" * 32, "application/octet-stream")},
            ).status_code
            == 201
        )
        over = app.post(
            FILES, files={"upload": ("b.bin", b"b" * 32, "application/octet-stream")}
        )
        assert over.status_code == 403
        assert over.json()["error"]["code"] == "QUOTA_EXCEEDED"


def test_max_file_size_and_metadata_caps(tmp_path: Path):
    with _custom_app(tmp_path, max_file_size=16) as app:
        big = app.post(
            FILES, files={"upload": ("big.bin", b"x" * 17, "application/octet-stream")}
        )
        assert big.status_code == 413
        assert big.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
        small = app.post(
            FILES, files={"upload": ("ok.bin", b"x" * 16, "application/octet-stream")}
        )
        assert small.status_code == 201

    with _custom_app(tmp_path, max_metadata_bytes=32) as app:
        fat = app.post(
            RECORDS,
            json={"namespace": "quota", "key": "fat", "value": {}, "metadata": {"blob": "x" * 100}},
        )
        assert fat.status_code == 413
        assert fat.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"

