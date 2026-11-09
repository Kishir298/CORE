"""File API endpoint tests."""

from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

BASE = "/api/v1/files"


def test_upload_and_metadata(client: TestClient):
    data = b"file-content-bytes"
    response = client.post(
        BASE, files={"upload": ("notes.txt", data, "text/plain")}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "notes.txt"
    assert body["mime_type"] == "text/plain"
    assert body["size"] == len(data)
    assert body["sha256"] == hashlib.sha256(data).hexdigest()
    assert body["version"] == 1


def test_metadata_lookup(client: TestClient):
    created = client.post(BASE, files={"upload": ("a.bin", b"x", None)}).json()
    response = client.get(f"{BASE}/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_download_content(client: TestClient):
    data = b"payload"
    created = client.post(BASE, files={"upload": ("p.bin", data, "application/octet-stream")}).json()
    response = client.get(f"{BASE}/{created['id']}/content")
    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["etag"]
    assert response.headers["x-file-sha256"] == created["sha256"]


def test_missing_file(client: TestClient):
    assert client.get(f"{BASE}/no-id").status_code == 404
    assert client.get(f"{BASE}/no-id/content").status_code == 404


def test_delete_file(client: TestClient):
    created = client.post(BASE, files={"upload": ("d.txt", b"x", "text/plain")}).json()
    response = client.delete(f"{BASE}/{created['id']}")
    assert response.status_code == 204
    assert client.get(f"{BASE}/{created['id']}").status_code == 404


def test_list_files(client: TestClient):
    client.post(BASE, files={"upload": ("one.txt", b"1", "text/plain")})
    client.post(BASE, files={"upload": ("two.txt", b"2", "text/plain")})
    response = client.get(BASE)
    assert response.status_code == 200
    assert response.json()["total"] == 2


def test_upload_requires_file(client: TestClient):
    response = client.post(BASE)
    assert response.status_code == 422


def test_oversized_upload_rejected_during_intake():
    """Total-intake bound: 413 before spool disk can fill."""
    from rescs.config import Settings
    from rescs.main import create_app

    settings = Settings(
        api_key="test-key-12345678",
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        storage_dir="rescs_test_storage",
        max_file_size=16,
        _env_file=None,
    )
    app = create_app(settings=settings)
    with TestClient(app, headers={"X-API-Key": settings.api_key}) as limited:
        response = limited.post(
            BASE, files={"upload": ("big.bin", b"x" * 64, "application/octet-stream")}
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_content_disposition_sanitizes_hostile_filename(client: TestClient):
    from rescs.api.routers.files import _content_disposition

    # Raw attacker-controlled name (bypasses any transport encoding).
    hostile = 'evil"\r\nX-Injected: yes'
    disposition = _content_disposition(hostile)
    # Security properties: no line breaks (header split) and no quote
    # inside the quoted filename segment (breakout). The leftover
    # "X-Injected: yes" is inert quoted text, not a header.
    assert "\r" not in disposition and "\n" not in disposition
    quoted = disposition.split('filename="', 1)[1].split('"', 1)[0]
    assert '"' not in quoted
    assert disposition.startswith("attachment;")

    # End-to-end: served header never carries raw CR/LF either.
    created = client.post(
        BASE, files={"upload": ("my file.txt", b"data", "text/plain")}
    )
    assert created.status_code == 201
    served = client.get(f"{BASE}/{created.json()['id']}/content")
    assert served.status_code == 200
    assert "\r" not in served.headers["content-disposition"]


def test_content_disposition_keeps_plain_filename(client: TestClient):
    created = client.post(
        BASE, files={"upload": ("my file.txt", b"data", "text/plain")}
    ).json()
    response = client.get(f"{BASE}/{created['id']}/content")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        'attachment; filename="my file.txt"; '
        "filename*=UTF-8''my%20file.txt"
    )
