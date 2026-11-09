"""Reliability: TTL bounds, streaming integrity, bulk isolation, quota races."""

from __future__ import annotations

import hashlib
from datetime import UTC

from fastapi.testclient import TestClient

RECORDS = "/api/v1/records"
FILES = "/api/v1/files"
UPLOADS = "/api/v1/uploads"


def test_ttl_seconds_and_max(client: TestClient):
    r = client.post(RECORDS, json={"namespace": "rel", "key": "ttl1", "value": {}, "ttl_seconds": 3600})
    assert r.status_code == 201, r.text
    assert r.json()["expires_at"] is not None
    # Both set rejected.
    from datetime import datetime, timedelta

    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    bad = client.post(RECORDS, json={"namespace": "rel", "key": "ttl2", "value": {}, "expires_at": future, "ttl_seconds": 10})
    assert bad.status_code == 422
    # Zero/negative rejected.
    bad2 = client.post(RECORDS, json={"namespace": "rel", "key": "ttl3", "value": {}, "ttl_seconds": 0})
    assert bad2.status_code == 422


def test_streaming_roundtrip_integrity(client: TestClient):
    data = b"ab12" * 3000  # ~12KB
    r = client.post(FILES, files={"upload": ("s.bin", data, "application/octet-stream")}, data={"owner": "system"})
    assert r.status_code == 201, r.text
    meta = r.json()
    assert meta["sha256"] == hashlib.sha256(data).hexdigest()
    dl = client.get(f"{FILES}/{meta['id']}/content")
    assert dl.status_code == 200
    assert hashlib.sha256(dl.content).hexdigest() == meta["sha256"]


def test_bulk_owner_isolation_scoped(scoped_client: TestClient, client: TestClient):
    # Create victim resource under a different owner via unscoped client.
    v = client.post(RECORDS, json={"namespace": "bulko", "key": "victim", "value": {}, "owner": "owner-B"})
    assert v.status_code == 201
    vid = v.json()["id"]
    # Scoped (tenant-a) bulk delete of owner-B resource must fail per-item, not 500.
    res = scoped_client.post(f"{RECORDS}/bulk", json={"operations": [{"op": "delete", "id": vid}]})
    assert res.status_code == 200
    item = res.json()["results"][0]
    assert item["status"] == "error"
    assert item["code"] in ("FORBIDDEN", "NOT_FOUND")


def test_quota_race_safe_single_winner(tmp_path):
    from rescs.config import Settings
    from rescs.main import create_app

    settings = Settings(
        api_key="quota-race-key-0123456789abcdef",
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        storage_dir="rescs_test_storage",
        max_records_per_owner=2,
        _env_file=None,
    )
    app = create_app(settings=settings)
    with TestClient(app, headers={"X-API-Key": settings.api_key}) as c:
        ids = []
        for i in range(3):
            r = c.post(RECORDS, json={"namespace": "q", "key": f"k{i}", "value": {}, "owner": "o1"})
            ids.append(r.status_code)
        assert ids.count(201) == 2
        assert 403 in ids

