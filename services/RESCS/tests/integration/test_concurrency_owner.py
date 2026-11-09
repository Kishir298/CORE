"""Integration: optimistic concurrency, idempotency, owner boundaries.

Covers §10–§12 against real behavior (no invented semantics):

- ETag round-trip: fresh etag succeeds + rotates, stale etag -> 412 with
  ``current_etag``, no silent overwrite (explicit client-A / client-B
  simulation).
- Version monotonicity on every content-changing write.
- Idempotent record creates via HTTP; file idempotency at the service
  boundary (the upload route exposes no idempotency field, so HTTP-level
  file idempotency is NOT claimed).
- Owner scoping: multi-owner list filtering in default mode, single-owner
  lock (401) in scoped mode, and the 403 service/repository boundary.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rescs.errors import ForbiddenError, UnauthorizedError
from rescs.schemas.file_object import FileObjectCreate
from rescs.security import (
    assert_principal_is_owner,
    enforce_owner,
    scoped_query_owner,
)
from tests.conftest import SCOPED_OWNER

RECORDS = "/api/v1/records"
FILES = "/api/v1/files"


# --- concurrency: client A vs client B --------------------------------------


def test_concurrent_patch_stale_etag_loses(client: TestClient):
    created = client.post(
        RECORDS, json={"namespace": "cc", "key": "shared", "value": {"n": 1}}
    ).json()
    record_id = created["id"]
    etag_n1 = created["etag"]

    # Client B updates first using the fresh etag.
    b_wins = client.patch(
        f"{RECORDS}/{record_id}",
        json={"value": {"n": 2}},
        headers={"If-Match": etag_n1},
    )
    assert b_wins.status_code == 200
    assert b_wins.json()["version"] == 2
    etag_n2 = b_wins.json()["etag"]
    assert etag_n2 != etag_n1

    # Client A retries with the now-stale etag: must lose loudly.
    a_loses = client.patch(
        f"{RECORDS}/{record_id}",
        json={"value": {"n": 99}},
        headers={"If-Match": etag_n1},
    )
    assert a_loses.status_code == 412
    error = a_loses.json()["error"]
    assert error["code"] == "PRECONDITION_FAILED"
    assert error["details"]["current_etag"] == etag_n2

    # No silent overwrite: stored value is still B's, version unchanged.
    current = client.get(f"{RECORDS}/{record_id}").json()
    assert current["value"] == {"n": 2}
    assert current["version"] == 2
    assert current["etag"] == etag_n2


def test_put_and_delete_require_fresh_etag(client: TestClient):
    client.put(RECORDS, json={"namespace": "cc", "key": "guarded", "value": {"n": 1}})
    stale_put = client.put(
        RECORDS,
        json={"namespace": "cc", "key": "guarded", "value": {"n": 2}},
        headers={"If-Match": "stale-etag"},
    )
    assert stale_put.status_code == 412

    created = client.post(
        RECORDS, json={"namespace": "cc", "key": "del-guard", "value": {}}
    ).json()
    bad_delete = client.delete(
        f"{RECORDS}/{created['id']}", headers={"If-Match": "wrong"}
    )
    assert bad_delete.status_code == 412
    assert client.get(f"{RECORDS}/{created['id']}").status_code == 200
    good_delete = client.delete(
        f"{RECORDS}/{created['id']}", headers={"If-Match": created["etag"]}
    )
    assert good_delete.status_code == 204


def test_file_delete_requires_fresh_etag(client: TestClient):
    uploaded = client.post(
        FILES, files={"upload": ("g.bin", b"guarded", "application/octet-stream")}
    ).json()
    file_id = uploaded["id"]
    assert (
        client.delete(f"{FILES}/{file_id}", headers={"If-Match": "stale"}).status_code
        == 412
    )
    assert client.get(f"{FILES}/{file_id}").status_code == 200
    assert (
        client.delete(
            f"{FILES}/{file_id}", headers={"If-Match": uploaded["etag"]}
        ).status_code
        == 204
    )


def test_versions_increase_monotonically(client: TestClient):
    created = client.post(
        RECORDS, json={"namespace": "cc", "key": "mono", "value": {"n": 0}}
    ).json()
    seen = [created["version"]]
    for index in range(1, 4):
        updated = client.patch(
            f"{RECORDS}/{created['id']}", json={"value": {"n": index}}
        ).json()
        seen.append(updated["version"])
    assert seen == [1, 2, 3, 4]


# --- idempotency --------------------------------------------------------------


def test_record_idempotent_replay_returns_same_resource(client: TestClient):
    payload = {
        "namespace": "idem",
        "key": "order-1",
        "value": {"item": "book"},
        "idempotency_key": "order-123-retry-1",
    }
    first = client.post(RECORDS, json=payload)
    second = client.post(RECORDS, json=payload)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    listed = client.get(f"{RECORDS}?namespace=idem").json()
    assert listed["total"] == 1


def test_record_idempotency_key_wins_over_payload_difference(client: TestClient):
    base = {
        "namespace": "idem",
        "key": "order-2",
        "value": {"item": "pen"},
        "idempotency_key": "order-456-retry-1",
    }
    first = client.post(RECORDS, json=base).json()
    replay = client.post(
        RECORDS, json={**base, "value": {"item": "DIFFERENT"}}
    ).json()
    assert replay["id"] == first["id"]
    assert replay["value"] == {"item": "pen"}


def test_file_idempotency_at_service_boundary(client: TestClient):
    """File idempotency exists at the service layer (schema supports the key).

    The multipart upload route exposes no idempotency field, so this is
    deliberately a service-level proof, not an HTTP claim.
    """
    services = client.app.state.services
    payload = FileObjectCreate(
        filename="idem.bin", owner="system", idempotency_key="file-idem-1"
    )
    first = services.files.create(payload, b"same-bytes")
    second = services.files.create(payload, b"same-bytes")
    assert first.id == second.id
    assert services.files.list().total >= 1


# --- owner scoping --------------------------------------------------------------


def test_multi_owner_list_filtering_isolates(client: TestClient):
    client.post(
        RECORDS,
        json={"namespace": "own", "key": "a-1", "value": {}, "owner": "owner-A"},
    )
    client.post(
        RECORDS,
        json={"namespace": "own", "key": "b-1", "value": {}, "owner": "owner-B"},
    )
    only_a = client.get(f"{RECORDS}?namespace=own&owner=owner-A").json()
    only_b = client.get(f"{RECORDS}?namespace=own&owner=owner-B").json()
    assert only_a["total"] == 1
    assert only_a["items"][0]["owner"] == "owner-A"
    assert only_b["total"] == 1
    assert only_b["items"][0]["owner"] == "owner-B"

    client.post(FILES, files={"upload": ("a.txt", b"a", "text/plain")}, data={"owner": "owner-A"})
    client.post(FILES, files={"upload": ("b.txt", b"b", "text/plain")}, data={"owner": "owner-B"})
    files_a = client.get(f"{FILES}?owner=owner-A").json()
    assert files_a["total"] == 1
    assert files_a["items"][0]["owner"] == "owner-A"


def test_scoped_mode_locks_writes_and_filters(scoped_client: TestClient):
    ok = scoped_client.post(
        RECORDS,
        json={"namespace": "own", "key": "s-1", "value": {}, "owner": SCOPED_OWNER},
    )
    assert ok.status_code == 201
    rogue_write = scoped_client.post(
        RECORDS,
        json={"namespace": "own", "key": "rogue", "value": {}, "owner": "owner-B"},
    )
    assert rogue_write.status_code == 401
    assert rogue_write.json()["error"]["code"] == "UNAUTHORIZED"
    rogue_filter = scoped_client.get(f"{RECORDS}?owner=owner-B")
    assert rogue_filter.status_code == 401


def test_service_boundary_enforces_ownership(scoped_client: TestClient):
    """The 403 cross-owner guard lives below the routes (service/repo seam)."""
    settings = scoped_client.app.state.settings
    assert settings.api_key_owner == SCOPED_OWNER
    # Claiming another owner on write is rejected at the boundary.
    with pytest.raises(UnauthorizedError):
        enforce_owner(requested="owner-B", principal=SCOPED_OWNER, settings=settings)
    # Filtering by another owner is rejected at the boundary.
    with pytest.raises(UnauthorizedError):
        scoped_query_owner(owner="owner-B", principal=SCOPED_OWNER, settings=settings)
    # Touching another owner's resource is forbidden at the boundary.
    with pytest.raises(ForbiddenError) as exc_info:
        assert_principal_is_owner(
            record_owner="owner-B", principal=SCOPED_OWNER, settings=settings
        )
    assert exc_info.value.code == "FORBIDDEN"
    # Own resources pass through untouched.
    assert (
        enforce_owner(requested=SCOPED_OWNER, principal=SCOPED_OWNER, settings=settings)
        == SCOPED_OWNER
    )

