"""Integration: full record + file lifecycle through the HTTP API.

Covers §8.1/§8.2 over the real stack (SQLAlchemy backend + local object
store via the shared ``client`` fixture): valid/invalid requests, auth
matrix, nonexistent resources, pagination, empty results, malformed
parameters, content integrity, and failed-upload consistency.
"""

from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

RECORDS = "/api/v1/records"
FILES = "/api/v1/files"


def _record(**overrides):
    values = {"namespace": "default", "key": "k", "value": {"v": 1}}
    values.update(overrides)
    return values


# --- records: full lifecycle ------------------------------------------------


def test_record_full_lifecycle(client: TestClient):
    created = client.post(RECORDS, json=_record(key="life-1")).json()
    record_id = created["id"]
    assert created["version"] == 1

    got = client.get(f"{RECORDS}/{record_id}")
    assert got.status_code == 200
    assert got.json()["value"] == {"v": 1}

    patched = client.patch(f"{RECORDS}/{record_id}", json={"value": {"v": 2}})
    assert patched.status_code == 200
    assert patched.json()["version"] == 2
    assert patched.json()["value"] == {"v": 2}

    upserted = client.put(
        RECORDS, json=_record(key="life-1", value={"v": 3})
    )
    assert upserted.status_code == 200
    assert upserted.json()["id"] == record_id
    assert upserted.json()["version"] == 3

    listed = client.get(f"{RECORDS}?namespace=default")
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1

    deleted = client.delete(f"{RECORDS}/{record_id}")
    assert deleted.status_code == 204
    assert client.get(f"{RECORDS}/{record_id}").status_code == 404
    # Second delete of the same id is a clean 404, not a 500.
    assert client.delete(f"{RECORDS}/{record_id}").status_code == 404


def test_record_auth_matrix(client: TestClient):
    payload = _record(key="auth-matrix")
    assert client.post(RECORDS, json=payload, headers={"X-API-Key": ""}).status_code == 401
    assert (
        client.post(RECORDS, json=payload, headers={"X-API-Key": "wrong-key-0000000000"}).status_code
        == 401
    )
    assert client.get(RECORDS, headers={"X-API-Key": ""}).status_code == 401


def test_record_invalid_and_malformed(client: TestClient):
    # Schema violation -> 422 envelope.
    bad = client.post(RECORDS, json=_record(namespace="not valid!"))
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"
    # Empty PATCH body -> 400 INVALID_REQUEST.
    created = client.post(RECORDS, json=_record(key="mal-1")).json()
    empty = client.patch(f"{RECORDS}/{created['id']}", json={})
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "INVALID_REQUEST"
    # Malformed pagination -> 422, not a crash.
    assert client.get(f"{RECORDS}?limit=0").status_code == 422
    assert client.get(f"{RECORDS}?limit=501").status_code == 422
    assert client.get(f"{RECORDS}?offset=-1").status_code == 422


def test_record_pagination_and_empty_results(client: TestClient):
    for index in range(3):
        client.post(RECORDS, json=_record(namespace="page-ns", key=f"p-{index}"))
    page = client.get(f"{RECORDS}?namespace=page-ns&limit=2&offset=0").json()
    assert page["total"] == 3
    assert len(page["items"]) == 2
    assert page["limit"] == 2 and page["offset"] == 0
    second = client.get(f"{RECORDS}?namespace=page-ns&limit=2&offset=2").json()
    assert len(second["items"]) == 1
    empty = client.get(f"{RECORDS}?namespace=no-such-namespace-xyz").json()
    assert empty["total"] == 0 and empty["items"] == []


# --- files: full lifecycle --------------------------------------------------


def test_file_full_lifecycle_with_integrity(client: TestClient):
    data = b"lifecycle-bytes-" * 128
    digest = hashlib.sha256(data).hexdigest()
    upload = client.post(
        FILES, files={"upload": ("doc.txt", data, "text/plain")}
    )
    assert upload.status_code == 201, upload.text
    meta = upload.json()
    file_id = meta["id"]
    assert meta["size"] == len(data)
    assert meta["sha256"] == digest
    assert meta["mime_type"] == "text/plain"
    assert meta["version"] == 1
    assert meta["etag"]

    reread = client.get(f"{FILES}/{file_id}")
    assert reread.status_code == 200
    assert reread.json()["sha256"] == digest

    download = client.get(f"{FILES}/{file_id}/content")
    assert download.status_code == 200
    assert download.content == data
    assert download.headers["x-file-sha256"] == digest
    assert download.headers["x-file-size"] == str(len(data))
    assert download.headers["content-type"].split(";")[0] == "text/plain"
    assert download.headers["etag"]

    assert client.delete(f"{FILES}/{file_id}").status_code == 204
    assert client.get(f"{FILES}/{file_id}").status_code == 404
    assert client.get(f"{FILES}/{file_id}/content").status_code == 404
    assert client.delete(f"{FILES}/{file_id}").status_code == 404


def test_file_missing_and_invalid(client: TestClient):
    assert client.get(f"{FILES}/does-not-exist").status_code == 404
    assert client.get(f"{FILES}/does-not-exist/content").status_code == 404
    # No multipart part at all -> 422.
    assert client.post(FILES).status_code == 422


def test_failed_consistency_no_orphan_metadata(client: TestClient):
    """A download for a metadata row whose blob is gone must fail loudly.

    The metadata row exists, but content cannot be served: STORAGE_ERROR
    (never a truncated/garbage 200).
    """
    data = b"orphan-check"
    created = client.post(
        FILES, files={"upload": ("orphan.bin", data, "application/octet-stream")}
    ).json()
    file_id = created["id"]
    store = client.app.state.services.files.object_store
    store.delete(file_id)
    assert store.exists(file_id) is False
    response = client.get(f"{FILES}/{file_id}/content")
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] == "STORAGE_ERROR"
    # Metadata still reports the expected digest (evidence, not a lie).
    assert client.get(f"{FILES}/{file_id}").json()["sha256"] == created["sha256"]

