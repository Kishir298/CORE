"""Record API endpoint tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

BASE = "/api/v1/records"


def create_payload(**overrides):
    values = dict(namespace="default", key="k", value={"a": 1})
    values.update(overrides)
    return values


def test_create_record(client: TestClient):
    response = client.post(BASE, json=create_payload(key="greeting"))
    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["namespace"] == "default"
    assert body["key"] == "greeting"
    assert body["value"] == {"a": 1}
    assert body["version"] == 1
    assert body["etag"]
    assert body["owner"] == "system"


def test_duplicate_namespace_key_conflicts(client: TestClient):
    payload = create_payload(namespace="ns", key="same")
    assert client.post(BASE, json=payload).status_code == 201
    response = client.post(BASE, json=payload)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_get_record(client: TestClient):
    created = client.post(BASE, json=create_payload(key="x")).json()
    response = client.get(f"{BASE}/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_missing_record(client: TestClient):
    response = client.get(f"{BASE}/no-such-id")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_put_upserts(client: TestClient):
    first = client.put(BASE, json=create_payload(namespace="n", key="k", value={"v": 1}))
    assert first.status_code == 200
    first_id = first.json()["id"]

    second = client.put(BASE, json=create_payload(namespace="n", key="k", value={"v": 2}))
    assert second.status_code == 200
    assert second.json()["id"] == first_id
    assert second.json()["version"] == 2
    assert second.json()["value"] == {"v": 2}


def test_patch_updates_partially(client: TestClient):
    created = client.post(BASE, json=create_payload(key="k", value={"a": 1})).json()
    response = client.patch(f"{BASE}/{created['id']}", json={"value": {"a": 2}})
    assert response.status_code == 200
    body = response.json()
    assert body["value"] == {"a": 2}
    assert body["version"] == 2


def test_patch_without_fields_rejected(client: TestClient):
    created = client.post(BASE, json=create_payload(key="k")).json()
    response = client.patch(f"{BASE}/{created['id']}", json={})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_delete_record(client: TestClient):
    created = client.post(BASE, json=create_payload(key="k")).json()
    response = client.delete(f"{BASE}/{created['id']}")
    assert response.status_code == 204
    assert client.get(f"{BASE}/{created['id']}").status_code == 404


def test_list_records_with_pagination(client: TestClient):
    for index in range(5):
        client.post(BASE, json=create_payload(namespace="orders", key=f"o-{index}"))
    response = client.get(f"{BASE}?namespace=orders&limit=2&offset=1")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["limit"] == 2
    assert body["offset"] == 1


def test_search_records(client: TestClient):
    client.post(BASE, json=create_payload(key="alpha", value={"note": "blue"}))
    client.post(BASE, json=create_payload(key="beta", value={"note": "red"}))
    response = client.get(f"{BASE}?query=blue")
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_validation_error_envelope(client: TestClient):
    response = client.post(BASE, json=create_payload(key="k", namespace="not valid!"))
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["errors"]
