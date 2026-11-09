"""Integration: persistent audit logging (Phase 22).

Every important storage operation leaves a secret-free audit event carrying
timestamp, operation, resource identity, owner, request ID, and outcome.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

RECORDS = "/api/v1/records"
FILES = "/api/v1/files"
AUDIT = "/api/v1/admin/audit"


def _events(client: TestClient, **params) -> list[dict]:
    response = client.get(AUDIT, params=params)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_mutations_emit_audit_events(client: TestClient):
    created = client.post(
        RECORDS,
        json={"namespace": "au", "key": "doc", "value": {}},
        headers={"X-Request-ID": "audit-trace-1"},
    ).json()
    client.patch(f"{RECORDS}/{created['id']}", json={"value": {"v": 2}})
    client.delete(f"{RECORDS}/{created['id']}")
    client.post(f"{RECORDS}/{created['id']}/restore")
    client.delete(f"{RECORDS}/{created['id']}/purge")

    operations = [event["operation"] for event in _events(client, owner="system")]
    for expected in (
        "record.create",
        "record.update",
        "record.delete",
        "record.restore",
        "record.purge",
    ):
        assert expected in operations, operations

    created_event = next(
        event
        for event in _events(client, operation="record.create")
        if event["resource_id"] == created["id"]
    )
    assert created_event["resource_type"] == "record"
    assert created_event["owner"] == "system"
    assert created_event["outcome"] == "ok"
    assert created_event["request_id"] == "audit-trace-1"
    assert created_event["timestamp"]


def test_file_and_failure_outcomes_audited(client: TestClient):
    uploaded = client.post(
        FILES, files={"upload": ("au.bin", b"audit-bytes", "application/octet-stream")}
    ).json()
    client.get(f"{FILES}/{uploaded['id']}/content")
    client.get(f"{RECORDS}/no-such-id")  # a 404 read is not audited (no mutation)

    operations = [event["operation"] for event in _events(client)]
    assert "file.upload" in operations
    assert "file.download" in operations

    # Failed mutation records the error outcome + code.
    doomed = client.post(
        RECORDS, json={"namespace": "au", "key": "condemned", "value": {}}
    ).json()
    bad_delete = client.delete(
        f"{RECORDS}/{doomed['id']}", headers={"If-Match": "stale-etag"}
    )
    assert bad_delete.status_code == 412
    failures = [
        event
        for event in _events(client, operation="record.delete")
        if event["resource_id"] == doomed["id"] and event["outcome"] == "error"
    ]
    assert failures and failures[0]["error_code"] == "PRECONDITION_FAILED"


def test_audit_contains_no_secrets(client: TestClient, settings):
    client.post(
        RECORDS, json={"namespace": "au", "key": "s", "value": {"password": "hunter2"}}
    )
    client.post(
        FILES, files={"upload": ("s.bin", b"secret-bytes", "application/octet-stream")}
    )
    text = json.dumps(_events(client)).lower()
    assert settings.api_key.lower() not in text
    for token in ("hunter2", "secret-bytes", "x-api-key", "authorization", "traceback"):
        assert token not in text


def test_audit_owner_scoping(scoped_client: TestClient):
    from tests.conftest import SCOPED_OWNER

    scoped_client.post(
        RECORDS,
        json={"namespace": "au", "key": "k", "value": {}, "owner": SCOPED_OWNER},
    )
    own = scoped_client.get(AUDIT).json()
    assert own["total"] >= 1
    assert all(event["owner"] == SCOPED_OWNER for event in own["items"])
    denied = scoped_client.get(f"{AUDIT}?owner=someone-else")
    assert denied.status_code == 401


def test_audit_retention_prune(client: TestClient):
    client.post(RECORDS, json={"namespace": "au", "key": "prune-me", "value": {}})
    services = client.app.state.services
    cutoff = datetime.now(UTC) + timedelta(seconds=1)
    pruned = services.audit.prune_before(cutoff)
    assert pruned >= 1
    assert client.get(AUDIT).json()["total"] == 0

