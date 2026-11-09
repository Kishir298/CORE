"""Unit: S3 abstraction (fake backend, no credentials)."""

from __future__ import annotations

import pytest

from rescs.config import Settings
from rescs.errors import ConfigurationError
from rescs.storage.s3 import FakeS3ObjectStore, build_object_store


def test_fake_s3_roundtrip():
    store = FakeS3ObjectStore(bucket="b", prefix="pfx")
    store.put("a", b"hello")
    assert store.get("a") == b"hello"
    assert store.exists("a")
    assert store.size("a") == 5
    assert list(store.get_stream("a", chunk_size=2)) == [b"he", b"ll", b"o"]
    store.put_stream("b", [b"x", b"yy"])
    assert store.get("b") == b"xyy"
    store.delete("a")
    assert not store.exists("a")


def test_build_object_store_memory_and_fake():
    s = Settings(api_key="test-key-12345678", storage_backend="memory", _env_file=None)
    assert build_object_store(s).__class__.__name__ == "MemoryObjectStore"
    s2 = Settings(
        api_key="test-key-12345678",
        storage_backend="s3",
        s3_endpoint="fake:local",
        s3_bucket="",
        _env_file=None,
    )
    assert isinstance(build_object_store(s2), FakeS3ObjectStore)


def test_build_object_store_s3_missing_bucket_fails_fast():
    s = Settings(api_key="test-key-12345678", storage_backend="s3", s3_bucket="", _env_file=None)
    with pytest.raises(ConfigurationError, match="RESCS_S3_BUCKET"):
        build_object_store(s)


def test_build_object_store_s3_missing_bucket_message_names_var():
    from rescs.config import Settings
    from rescs.errors import ConfigurationError

    s = Settings(api_key="test-key-12345678", storage_backend="s3", s3_bucket="", _env_file=None)
    with pytest.raises(ConfigurationError) as excinfo:
        build_object_store(s)
    assert "RESCS_S3_BUCKET" in str(excinfo.value)

