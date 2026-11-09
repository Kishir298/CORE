"""HTTP-level synchronization tests (If-Match, ETag, idempotency)."""

from __future__ import annotations

from fastapi.testclient import TestClient

BASE = "/api/v1/records"


def _record(**overrides):
    values = {"namespace": "default", "key": "k", "value": {"v": 1}, "owner": "system"}
    values.update(overrides)
    return values


def test_create_returns_etag_header(client: TestClient):
    response = client.post(BASE, json=_record())
    assert response.status_code == 201
    assert response.headers["etag"]
    assert "etag" in response.json()


def test_patch_with_correct_if_match(client: TestClient):
    created = client.post(BASE, json=_record()).json()
    etag = created["etag"]
    response = client.patch(
        f"{BASE}/{created['id']}",
        json={"value": {"v": 2}},
        headers={"If-Match": etag},
    )
    assert response.status_code == 200
    assert response.json()["version"] == 2


def test_patch_with_stale_if_match_returns_412(client: TestClient):
    created = client.post(BASE, json=_record()).json()
    response = client.patch(
        f"{BASE}/{created['id']}",
        json={"value": {"v": 2}},
        headers={"If-Match": "stale-etag"},
    )
    assert response.status_code == 412
    error = response.json()["error"]
    assert error["code"] == "PRECONDITION_FAILED"
    assert error["details"]["current_etag"] == created["etag"]


def test_patch_with_quoted_if_match(client: TestClient):
    created = client.post(BASE, json=_record()).json()
    response = client.patch(
        f"{BASE}/{created['id']}",
        json={"value": {"v": 3}},
        headers={"If-Match": f'W/"{created["etag"]}"'},
    )
    assert response.status_code == 200


def test_put_with_if_match_when_absent_returns_412(client: TestClient):
    response = client.put(
        BASE, json=_record(), headers={"If-Match": "anything"}
    )
    assert response.status_code == 412


def test_put_with_stale_if_match_returns_412(client: TestClient):
    client.put(BASE, json=_record(key="k"))
    response = client.put(
        BASE, json=_record(key="k", value={"v": 9}), headers={"If-Match": "stale"}
    )
    assert response.status_code == 412


def test_delete_record_with_if_match(client: TestClient):
    created = client.post(BASE, json=_record()).json()
    response = client.delete(
        f"{BASE}/{created['id']}", headers={"If-Match": created["etag"]}
    )
    assert response.status_code == 204


def test_delete_record_with_stale_if_match(client: TestClient):
    created = client.post(BASE, json=_record()).json()
    response = client.delete(
        f"{BASE}/{created['id']}", headers={"If-Match": "wrong"}
    )
    assert response.status_code == 412
    assert client.get(f"{BASE}/{created['id']}").status_code == 200


def test_idempotent_create_returns_existing(client: TestClient):
    payload = _record(key="unique-key")
    payload["idempotency_key"] = "http-idem-1"
    first = client.post(BASE, json=payload).json()
    second = client.post(BASE, json=payload).json()
    assert first["id"] == second["id"]


def test_upload_and_delete_file_with_if_match(client: TestClient):
    upload = client.post(
        "/api/v1/files", files={"upload": ("f.bin", b"data", "application/octet-stream")}
    )
    assert upload.status_code == 201
    file_id = upload.json()["id"]
    etag = upload.json()["etag"]
    response = client.delete(
        f"/api/v1/files/{file_id}", headers={"If-Match": etag}
    )
    assert response.status_code == 204
