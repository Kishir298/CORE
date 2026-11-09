"""Integration: live S3 round-trip gate.

Fake-only stays the deterministic default (see tests/unit/test_storage_s3.py).
These tests only execute when RESCS_LIVE_S3_* point at a real bucket;
otherwise they skip cleanly. They never silently fall back to FakeS3
when live S3 was explicitly requested.
"""

from __future__ import annotations

import os
import uuid

import pytest

LIVE_ENDPOINT = os.environ.get("RESCS_LIVE_S3_ENDPOINT", "")
LIVE_BUCKET = os.environ.get("RESCS_LIVE_S3_BUCKET", "")
LIVE_REGION = os.environ.get("RESCS_LIVE_S3_REGION", "")
LIVE_ACCESS_KEY = os.environ.get("RESCS_LIVE_S3_ACCESS_KEY", "")
LIVE_SECRET_KEY = os.environ.get("RESCS_LIVE_S3_SECRET_KEY", "")
LIVE_PREFIX = os.environ.get("RESCS_LIVE_S3_PREFIX", "")

requires_live_s3 = pytest.mark.skipif(
    not (LIVE_ENDPOINT and LIVE_BUCKET and LIVE_ACCESS_KEY and LIVE_SECRET_KEY),
    reason="RESCS_LIVE_S3_* not configured; live S3 check deferred",
)


def test_live_s3_gate_skips_cleanly_when_unconfigured():
    if LIVE_ENDPOINT and LIVE_BUCKET and LIVE_ACCESS_KEY and LIVE_SECRET_KEY:
        pytest.skip("live S3 configured; gate test not applicable")
    assert not (LIVE_ENDPOINT and LIVE_BUCKET and LIVE_ACCESS_KEY and LIVE_SECRET_KEY)


@requires_live_s3
def test_live_s3_roundtrip():
    boto3 = pytest.importorskip("boto3")
    assert boto3 is not None
    from rescs.storage.s3 import S3ObjectStore

    prefix = (LIVE_PREFIX or f"test-{uuid.uuid4().hex[:8]}").strip("/")
    store = S3ObjectStore(
        endpoint=LIVE_ENDPOINT,
        bucket=LIVE_BUCKET,
        region=LIVE_REGION,
        access_key=LIVE_ACCESS_KEY,
        secret_key=LIVE_SECRET_KEY,
        prefix=prefix,
    )
    key = f"smoke-{uuid.uuid4().hex[:8]}"
    try:
        store.put(key, b"hello-live-s3")
        assert store.exists(key)
        assert store.get(key) == b"hello-live-s3"
        assert store.size(key) == len(b"hello-live-s3")
        assert b"".join(store.get_stream(key)) == b"hello-live-s3"
    finally:
        try:
            store.delete(key)
        except Exception:
            pass
    assert not store.exists(key)

