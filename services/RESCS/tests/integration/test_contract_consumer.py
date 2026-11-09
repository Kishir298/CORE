"""Integration: error envelope, CORE consumer contract, health/observability.

Covers §13–§16 + §19 from the outside in, behaving as an external HTTP
consumer (never importing CORE):

- Stable ``{"error": {"code", "message", "details"}}`` shape for 401/404/
  409/412/422/500, unknown routes, and method errors.
- No secret leakage (API key, tokens, connection strings, tracebacks,
  filesystem paths beyond the safe object id) in any error body.
- ``GET /api/v1/contract`` matches the documented transport/envelope/
  pagination/etag/owner guarantees a CORE client relies on.
- Health + request-ID behavior at application level.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

RECORDS = "/api/v1/records"
FILES = "/api/v1/files"


def _assert_envelope(response, *, code: str) -> None:
    assert response.headers.get("X-Request-ID"), "request id must propagate on errors"
    body = response.json()
    assert set(body.keys()) == {"error"}, body
    error = body["error"]
    assert error["code"] == code, error
    assert isinstance(error["message"], str) and error["message"]
    assert "details" in error


def _assert_no_secrets(response, settings) -> None:
    text = json.dumps(response.json(), default=str).lower()
    assert settings.api_key.lower() not in text
    for token in (
        "password",
        "passwd",
        "secret",
        "authorization",
        "traceback",
        "hunter2",
    ):
        assert token not in text
    db_url = (settings.database_url or "").lower()
    if "://" in db_url and not db_url.startswith("sqlite"):
        assert db_url not in text


def test_error_envelope_matrix(client: TestClient, settings):
    # 401 — missing key.
    r401 = client.get(RECORDS, headers={"X-API-Key": ""})
    assert r401.status_code == 401
    _assert_envelope(r401, code="UNAUTHORIZED")

    # 404 — unknown record.
    r404 = client.get(f"{RECORDS}/no-such-id")
    assert r404.status_code == 404
    _assert_envelope(r404, code="NOT_FOUND")

    # 409 — duplicate (namespace, key) without idempotency key.
    payload = {"namespace": "env", "key": "dup", "value": {}}
    assert client.post(RECORDS, json=payload).status_code == 201
    r409 = client.post(RECORDS, json=payload)
    assert r409.status_code == 409
    _assert_envelope(r409, code="CONFLICT")

    # 412 — stale precondition.
    created = client.post(
        RECORDS, json={"namespace": "env", "key": "pre", "value": {}}
    ).json()
    r412 = client.patch(
        f"{RECORDS}/{created['id']}", json={"value": {"x": 1}}, headers={"If-Match": "stale"}
    )
    assert r412.status_code == 412
    _assert_envelope(r412, code="PRECONDITION_FAILED")
    assert r412.json()["error"]["details"]["current_etag"] == created["etag"]

    # 422 — schema violation.
    r422 = client.post(RECORDS, json={"namespace": "bad ns!", "key": "k", "value": {}})
    assert r422.status_code == 422
    _assert_envelope(r422, code="VALIDATION_ERROR")

    for response in (r401, r404, r409, r412, r422):
        _assert_no_secrets(response, settings)


def test_storage_error_envelope_without_leak(client: TestClient, settings):
    created = client.post(
        FILES, files={"upload": ("leak.bin", b"leak-check", "application/octet-stream")}
    ).json()
    client.app.state.services.files.object_store.put(created["id"], b"tampered-bytes")
    response = client.get(f"{FILES}/{created['id']}/content")
    assert response.status_code == 500
    _assert_envelope(response, code="STORAGE_ERROR")
    details = response.json()["error"]["details"]
    assert details["expected_sha256"] and details["actual_sha256"]
    _assert_no_secrets(response, settings)


def test_unknown_route_and_method_errors_are_enveloped(client: TestClient, settings):
    r404 = client.get("/no-such-route-xyz")
    assert r404.status_code == 404
    _assert_envelope(r404, code="NOT_FOUND")
    _assert_no_secrets(r404, settings)
    # POST on a GET-only item route -> 405 mapped into the stable envelope.
    r405 = client.post(f"{RECORDS}/some-id", json={})
    assert r405.status_code == 405
    assert "error" in r405.json()
    assert r405.headers.get("X-Request-ID")


def test_core_consumer_contract_roundtrip(client: TestClient):
    """A hypothetical CORE client discovers and then exercises the API."""
    contract = client.get("/api/v1/contract")
    assert contract.status_code == 200
    body = contract.json()
    # Transport + auth discovery.
    assert body["auth"] == {"method": "header", "header": "X-API-Key"}
    assert body["endpoints"]["records"] == "/api/v1/records"
    assert body["endpoints"]["files"] == "/api/v1/files"
    # Pagination guarantee usable as documented.
    assert body["pagination"]["limit_max"] == 500
    page = client.get("/api/v1/records?limit=500&offset=0")
    assert page.status_code == 200
    assert {"items", "total", "limit", "offset"} <= set(page.json().keys())
    # ETag guarantee usable as documented.
    created = client.post(
        RECORDS,
        json={"namespace": "core.ops.runnables", "key": "r-1", "value": {"s": 1}},
        headers={"X-Request-ID": "core-roundtrip-1"},
    )
    assert created.status_code == 201
    assert created.headers.get("X-Request-ID") == "core-roundtrip-1"
    assert created.headers.get("ETag") or created.headers.get("etag")
    record = created.json()
    assert {"version", "etag", "created_at", "updated_at"} <= set(record.keys())
    guarded = client.patch(
        f"{RECORDS}/{record['id']}",
        json={"value": {"s": 2}},
        headers={"If-Match": record["etag"]},
    )
    assert guarded.status_code == 200
    assert guarded.json()["version"] == record["version"] + 1
    # Reserved namespaces advertised for CORE state.
    assert "core." in body["reserved_namespaces"]
    # Error envelope sample matches the real one.
    assert body["error_envelope"]["shape"] == {
        "error": {"code": "str", "message": "str", "details": "object|null"}
    }


def test_health_and_request_id_at_app_level(client: TestClient):
    live = client.get("/health/live")
    assert live.status_code == 200
    assert live.json()["status"] == "alive"
    assert live.headers.get("X-Request-ID")

    ready = client.get("/health/ready", headers={"X-Request-ID": "health-1"})
    assert ready.status_code == 200
    assert ready.json() == {
        "status": "ready",
        "checks": {"database": "ok", "storage": "ok"},
    }
    assert ready.headers.get("X-Request-ID") == "health-1"

    generated = client.get("/health/live", headers={"X-Request-ID": "x" * 200})
    assert generated.status_code == 200
    assert generated.headers.get("X-Request-ID") != "x" * 200

