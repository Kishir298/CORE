"""Integration: resumable uploads (create/chunk/status/finalize/cancel)."""

from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

UPLOADS = "/api/v1/uploads"
FILES = "/api/v1/files"


def test_upload_lifecycle(client: TestClient):
    data = b"hello-world-" * 1000  # ~12KB
    total = len(data)
    created = client.post(
        UPLOADS,
        json={"filename": "a.bin", "content_type": "application/octet-stream", "total_size": total, "chunk_size": 65536},
    )
    assert created.status_code == 201, created.text
    session = created.json()
    sid = session["id"]
    assert session["received_bytes"] == 0

    # Sequential chunks via ?offset=
    offset = 0
    chunk = 65536
    while offset < total:
        piece = data[offset : offset + chunk]
        r = client.put(f"{UPLOADS}/{sid}/chunks?offset={offset}", content=piece, headers={"Content-Type": "application/octet-stream"})
        assert r.status_code == 200, r.text
        offset += len(piece)

    status = client.get(f"{UPLOADS}/{sid}").json()
    assert status["received_bytes"] == total

    # Duplicate chunk is idempotent.
    dup = client.put(f"{UPLOADS}/{sid}/chunks?offset=0", content=data[:chunk], headers={"Content-Type": "application/octet-stream"})
    assert dup.status_code == 200

    # Finalize publishes a normal file.
    fin = client.post(f"{UPLOADS}/{sid}/finalize")
    assert fin.status_code == 200, fin.text
    meta = fin.json()
    assert meta["size"] == total
    assert meta["sha256"] == hashlib.sha256(data).hexdigest()

    # Download round-trips.
    dl = client.get(f"{FILES}/{meta['id']}/content")
    assert dl.status_code == 200
    assert dl.content == data


def test_upload_validation_and_isolation(client: TestClient, scoped_client: TestClient):
    # Invalid chunk size rejected.
    bad = client.post(UPLOADS, json={"filename": "x", "total_size": 10, "chunk_size": 10})
    assert bad.status_code == 422
    # Oversized chunk offset rejected.
    s = client.post(UPLOADS, json={"filename": "y", "total_size": 10}).json()
    over = client.put(f"{UPLOADS}/{s['id']}/chunks?offset=999", content=b"zz", headers={"Content-Type": "application/octet-stream"})
    assert over.status_code in (400, 422)
    # Cross-owner access denied: scoped client cannot read first client's session.
    other = scoped_client.get(f"{UPLOADS}/{s['id']}")
    assert other.status_code in (401, 403, 404)


def test_upload_cancel(client: TestClient):
    s = client.post(UPLOADS, json={"filename": "c.bin", "total_size": 5}).json()
    sid = s["id"]
    r = client.put(f"{UPLOADS}/{sid}/chunks?offset=0", content=b"hello", headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 200
    c = client.delete(f"{UPLOADS}/{sid}")
    assert c.status_code == 204
    assert client.get(f"{UPLOADS}/{sid}").status_code == 404


def test_upload_checksum_mismatch(client: TestClient):
    data = b"abcde"
    s = client.post(
        UPLOADS, json={"filename": "k.bin", "total_size": len(data), "checksum": "0" * 64}
    ).json()
    client.put(f"{UPLOADS}/{s['id']}/chunks?offset=0", content=data, headers={"Content-Type": "application/octet-stream"})
    fin = client.post(f"{UPLOADS}/{s['id']}/finalize")
    assert fin.status_code in (400, 422)


def _put(client: TestClient, sid: str, offset: int, data: bytes):
    return client.put(
        f"{UPLOADS}/{sid}/chunks?offset={offset}",
        content=data,
        headers={"Content-Type": "application/octet-stream"},
    )


def test_upload_large_streaming_finalize(client: TestClient):
    # ~2.5 MiB across chunk_size boundaries; exercises streaming finalize path.
    chunk_size = 262144  # 256 KiB (>= 64 KiB minimum)
    total = chunk_size * 9 + 12345
    data = bytes(i % 251 for i in range(total))
    s = client.post(
        UPLOADS, json={"filename": "big.bin", "total_size": total, "chunk_size": chunk_size}
    )
    assert s.status_code == 201, s.text
    sid = s.json()["id"]
    offset = 0
    while offset < total:
        piece = data[offset : offset + chunk_size]
        r = _put(client, sid, offset, piece)
        assert r.status_code == 200, r.text
        offset += len(piece)
    fin = client.post(f"{UPLOADS}/{sid}/finalize")
    assert fin.status_code == 200, fin.text
    meta = fin.json()
    assert meta["size"] == total
    assert meta["sha256"] == hashlib.sha256(data).hexdigest()
    dl = client.get(f"{FILES}/{meta['id']}/content")
    assert dl.status_code == 200
    assert hashlib.sha256(dl.content).hexdigest() == meta["sha256"]


def test_upload_missing_chunk_fails(client: TestClient):
    chunk_size = 65536
    total = chunk_size * 3
    s = client.post(UPLOADS, json={"filename": "gap.bin", "total_size": total, "chunk_size": chunk_size}).json()
    sid = s["id"]
    assert _put(client, sid, 0, b"g" * chunk_size).status_code == 200
    # Skip middle chunk; upload last chunk (offsets need not be contiguous for put).
    assert _put(client, sid, chunk_size * 2, b"h" * chunk_size).status_code == 200
    fin = client.post(f"{UPLOADS}/{sid}/finalize")
    assert fin.status_code in (400, 409, 422)


def test_upload_wrong_total_and_chunk_rules(client: TestClient):
    chunk_size = 65536
    # Intermediate chunk smaller than chunk_size must fail.
    s = client.post(UPLOADS, json={"filename": "r.bin", "total_size": chunk_size * 2, "chunk_size": chunk_size}).json()
    assert _put(client, s["id"], 0, b"x" * 100).status_code in (400, 422)
    # Empty chunk must fail.
    assert _put(client, s["id"], 0, b"").status_code in (400, 422)


def test_upload_expired_session_cannot_finalize(client: TestClient):
    from datetime import timedelta

    from rescs.domain import utcnow

    s = client.post(UPLOADS, json={"filename": "e.bin", "total_size": 3}).json()
    sid = s["id"]
    assert _put(client, sid, 0, b"abc").status_code == 200
    # Force expiry directly through services.
    services = client.app.state.services if hasattr(client, "app") else None
    assert services is not None
    session = services.uploads._sessions.get(sid)
    session.expires_at = utcnow() - timedelta(seconds=1)
    services.uploads._sessions.update(session)
    assert client.post(f"{UPLOADS}/{sid}/finalize").status_code == 404
    assert client.get(f"{UPLOADS}/{sid}").status_code == 404


def test_upload_use_after_cancel(client: TestClient):
    s = client.post(UPLOADS, json={"filename": "u.bin", "total_size": 5}).json()
    sid = s["id"]
    assert _put(client, sid, 0, b"hello").status_code == 200
    assert client.delete(f"{UPLOADS}/{sid}").status_code == 204
    assert _put(client, sid, 0, b"hello").status_code == 404
    assert client.post(f"{UPLOADS}/{sid}/finalize").status_code in (404, 409)
    assert client.delete(f"{UPLOADS}/{sid}").status_code == 404


def test_upload_retry_finalize_no_duplicate(client: TestClient):
    data = b"retry-me"
    s = client.post(UPLOADS, json={"filename": "rt.bin", "total_size": len(data)}).json()
    sid = s["id"]
    assert _put(client, sid, 0, data).status_code == 200
    first = client.post(f"{UPLOADS}/{sid}/finalize")
    assert first.status_code == 200, first.text
    fid = first.json()["id"]
    second = client.post(f"{UPLOADS}/{sid}/finalize")
    assert second.status_code in (404, 409)
    # Original file still intact; no duplicate created via retry.
    assert client.get(f"{FILES}/{fid}").status_code == 200


def test_upload_concurrent_finalize_single_winner(client: TestClient):
    import threading

    data = b"c" * 100000
    chunk_size = 65536
    total = len(data)
    s = client.post(UPLOADS, json={"filename": "cc.bin", "total_size": total, "chunk_size": chunk_size}).json()
    sid = s["id"]
    offset = 0
    while offset < total:
        piece = data[offset : offset + chunk_size]
        assert _put(client, sid, offset, piece).status_code == 200
        offset += len(piece)
    results: list[int] = []

    def _finalize():
        # Separate TestClient per thread would need lifespan; use service directly.
        services = client.app.state.services
        try:
            services.uploads.finalize(sid, actor="system")
            results.append(200)
        except Exception as exc:
            code = getattr(exc, "code", type(exc).__name__)
            results.append(409 if code in ("CONFLICT",) else 404)

    threads = [threading.Thread(target=_finalize) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(200) == 1, results
    assert len(results) == 4


def test_upload_chunk_finalize_cancel_isolation(client: TestClient, scoped_client: TestClient):
    data = b"secret-bytes-123"
    s = client.post(UPLOADS, json={"filename": "iso.bin", "total_size": len(data)}).json()
    sid = s["id"]
    assert scoped_client.put(f"{UPLOADS}/{sid}/chunks?offset=0", content=data, headers={"Content-Type": "application/octet-stream"}).status_code in (401, 403, 404)
    assert scoped_client.post(f"{UPLOADS}/{sid}/finalize").status_code in (401, 403, 404)
    assert scoped_client.delete(f"{UPLOADS}/{sid}").status_code in (401, 403, 404)
    # Owner can still complete after the attacks.
    assert _put(client, sid, 0, data).status_code == 200
    assert client.post(f"{UPLOADS}/{sid}/finalize").status_code == 200


def test_upload_cleanup_no_orphan_chunks(client: TestClient):
    store = client.app.state.services.files.object_store
    data = b"z" * 70000
    chunk_size = 65536
    total = len(data)
    s = client.post(UPLOADS, json={"filename": "cl.bin", "total_size": total, "chunk_size": chunk_size}).json()
    sid = s["id"]
    offset = 0
    while offset < total:
        piece = data[offset : offset + chunk_size]
        assert _put(client, sid, offset, piece).status_code == 200
        offset += len(piece)

    def _chunk_keys():
        keys: list[str] = []
        base = getattr(store, "_base", None)
        if base is not None:
            from pathlib import Path

            keys = [p.name for p in Path(base).glob(f"{sid}__chunk__*")]
        else:
            blobs = getattr(store, "_blobs", {})
            keys = [k for k in blobs.keys() if k.startswith(f"{sid}__chunk__")]
        return keys

    assert len(_chunk_keys()) >= 1
    assert client.post(f"{UPLOADS}/{sid}/finalize").status_code == 200
    assert _chunk_keys() == []

    # Cancel path also cleans chunks.
    s2 = client.post(UPLOADS, json={"filename": "cl2.bin", "total_size": 5}).json()
    sid2 = s2["id"]
    assert _put(client, sid2, 0, b"hello").status_code == 200
    assert client.delete(f"{UPLOADS}/{sid2}").status_code == 204
    blobs = getattr(store, "_blobs", None)
    if isinstance(blobs, dict):
        assert not [k for k in blobs.keys() if k.startswith(f"{sid2}__chunk__")]
    else:
        from pathlib import Path

        assert list(Path(store._base).glob(f"{sid2}__chunk__*")) == []


def test_concurrent_finalize_single_winner(client: TestClient):
    import concurrent.futures

    data = b"cas-lock-" * 500
    total = len(data)
    created = client.post(
        UPLOADS,
        json={"filename": "cas.bin", "content_type": "application/octet-stream", "total_size": total, "chunk_size": 65536},
    )
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    offset = 0
    while offset < total:
        piece = data[offset : offset + 65536]
        r = client.put(f"{UPLOADS}/{sid}/chunks?offset={offset}", content=piece, headers={"Content-Type": "application/octet-stream"})
        assert r.status_code == 200, r.text
        offset += len(piece)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: client.post(f"{UPLOADS}/{sid}/finalize").status_code, range(4)))
    # Single-process single-winner: exactly one finalize succeeds; losers
    # fail loudly (404 already-finalized / 409 conflict), never 200 twice.
    assert results.count(200) == 1
    assert all(code in (404, 409) for code in results if code != 200)

