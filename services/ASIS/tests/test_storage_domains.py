import pytest

from asis.integrations.rescs.client import StorageClient, StoredRecord
from asis.storage.domains import (
    CLOUD_BOUND_KINDS,
    LOCAL_ONLY_KINDS,
    DomainError,
    DomainRouter,
)
from asis.storage.migrate import migrate_records


class FakeClient(StorageClient):
    def __init__(self, *, available=True):
        self._available = available
        self.stored: dict[tuple[str, str], StoredRecord] = {}
        self.writes = 0

    @property
    def name(self):
        return "fake"

    def available(self):
        return self._available

    def store(self, record: StoredRecord) -> bool:
        self.writes += 1
        self.stored[(record.namespace, record.key)] = record
        return True

    def retrieve(self, key, namespace="default"):
        return self.stored.get((namespace, key))

    def search(self, query, namespace="default"):
        return [
            record
            for (namespace_, _), record in self.stored.items()
            if namespace_ == namespace and query in record.key
        ]

    def delete(self, key, namespace="default"):
        return self.stored.pop((namespace, key), None) is not None


def test_classify_kinds():
    router = DomainRouter()
    assert "sqlite-memory" in LOCAL_ONLY_KINDS
    assert "memory-export" in CLOUD_BOUND_KINDS
    assert router.classify("sqlite-memory") == "local-only"
    assert router.classify("memory-export") == "cloud-bound"
    with pytest.raises(DomainError):
        router.classify("nope")


def test_namespace_enforcement():
    router = DomainRouter()
    assert router.namespace_for("memory-export") == "asis.memory"
    with pytest.raises(DomainError):
        router.namespace_for("sqlite-memory")
    with pytest.raises(DomainError):
        router.check_namespace("tiviss.memory")
    permissive = DomainRouter(allow_foreign_namespaces=True)
    assert permissive.check_namespace("tiviss.memory") == "tiviss.memory"


def test_migrate_dry_run_writes_nothing():
    client = FakeClient()
    manifest = migrate_records(
        [{"key": "k1", "data": {"v": 1}}], client=client, dry_run=True
    )
    assert manifest["copied"] == ["k1"]
    assert client.writes == 0


def test_migrate_copies_and_skips_identical():
    client = FakeClient()
    records = [{"key": "k1", "data": {"v": 1}}]
    first = migrate_records(records, client=client, dry_run=False)
    assert first["copied"] == ["k1"]
    second = migrate_records(records, client=client, dry_run=False)
    assert second["skipped_identical"] == ["k1"]
    assert second["copied"] == []
    assert client.stored[("asis.memory", "k1")].data["_owner"] == "asis"


def test_migrate_changed_content_rewrites():
    client = FakeClient()
    migrate_records([{"key": "k1", "data": {"v": 1}}], client=client, dry_run=False)
    manifest = migrate_records(
        [{"key": "k1", "data": {"v": 2}}], client=client, dry_run=False
    )
    assert manifest["copied"] == ["k1"]
    assert client.stored[("asis.memory", "k1")].data["v"] == 2


def test_migrate_never_deletes_source():
    client = FakeClient()
    records = [{"key": "k1", "data": {"v": 1}}]
    snapshot = [dict(record) for record in records]
    migrate_records(records, client=client, dry_run=False)
    assert records == snapshot


def test_migrate_rejects_foreign_namespace():
    client = FakeClient()
    with pytest.raises(DomainError):
        migrate_records(
            [{"key": "k1", "data": {}}],
            client=client,
            namespace="tiviss.memory",
        )
    assert client.writes == 0


def test_migrate_invalid_records_reported():
    client = FakeClient()
    manifest = migrate_records(
        [{"nope": True}, {"key": "", "data": {}}], client=client, dry_run=False
    )
    assert manifest["failed"] == ["None", ""]
    assert manifest["copied"] == []


def test_migrate_requires_available_client():
    with pytest.raises(DomainError, match="not available"):
        migrate_records(
            [{"key": "k", "data": {}}], client=FakeClient(available=False)
        )


def test_migrate_records_failure_isolated():
    class Flaky(FakeClient):
        def store(self, record):
            if record.key == "bad":
                raise OSError("disk gone")
            return super().store(record)

    client = Flaky()
    manifest = migrate_records(
        [
            {"key": "good", "data": {"v": 1}},
            {"key": "bad", "data": {"v": 2}},
        ],
        client=client,
        dry_run=False,
    )
    assert manifest["copied"] == ["good"]
    assert manifest["failed"] == ["bad"]
