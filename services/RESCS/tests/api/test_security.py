"""API key authentication and owner-scoping tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

RECORDS = "/api/v1/records"


def _record(owner: str = "system"):
    return {"namespace": "default", "key": "k", "value": {"v": 1}, "owner": owner}


def test_missing_key_rejected(client: TestClient):
    response = client.post(RECORDS, json=_record(), headers={"X-API-Key": ""})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_invalid_key_rejected(client: TestClient):
    response = client.get(RECORDS, headers={"X-API-Key": "definitely-wrong"})
    assert response.status_code == 401


def test_valid_key_allowed(client: TestClient):
    assert client.post(RECORDS, json=_record()).status_code == 201


def test_health_endpoints_open(client: TestClient):
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200


def test_scoped_owner_lock_rejects_other_owner(scoped_client: TestClient):
    response = scoped_client.post(RECORDS, json=_record(owner="tenant-b"))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_scoped_owner_matches(scoped_client: TestClient):
    response = scoped_client.post(RECORDS, json=_record(owner="tenant-a"))
    assert response.status_code == 201
    assert response.json()["owner"] == "tenant-a"


def test_scoped_list_forces_owner(scoped_client: TestClient):
    scoped_client.post(RECORDS, json=_record(owner="tenant-a"))
    response = scoped_client.get(RECORDS)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["owner"] == "tenant-a"


def test_scoped_list_rejects_other_owner_filter(scoped_client: TestClient):
    response = scoped_client.get(RECORDS, params={"owner": "tenant-b"})
    assert response.status_code == 401
