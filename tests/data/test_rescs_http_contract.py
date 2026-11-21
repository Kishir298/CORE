"""Contract tests for the HTTP adapter and reader against R.E.S.C.S. v1."""

import pytest

from core.data.errors import DataAccessDenied
from core.data.rescs_reader import HttpDataReader
from core.rescs.adapter import HttpRescsAdapter
from core.resources.models import Resource
from core.runtime.history import RuntimeRecord

from .rescs_http_fixture import RescsFixture


@pytest.fixture()
def fixture():
    with RescsFixture() as running:
        yield running


def _adapter(fixture, *, fallback=False, suffix=""):
    return HttpRescsAdapter(
        endpoint=fixture.url + suffix,
        timeout=2.0,
        fallback=fallback,
        api_key=fixture.api_key,
    )


def _reader(fixture, scope="device-a", cross=False):
    return HttpDataReader(
        endpoint=fixture.url,
        owner_scope=scope,
        allow_cross_owner=cross,
        timeout=2.0,
        api_key=fixture.api_key,
    )


def _resource(resource_id="r1", owner="alice"):
    return Resource(
        resource_id=resource_id,
        name=f"Resource {resource_id}",
        resource_type="sensor",
        status="online",
        owner=owner,
        capabilities=["read"],
        metadata={"site": "lab"},
    )


def test_adapter_maps_resources_to_record_api(fixture):
    adapter = _adapter(fixture)
    adapter.persist_resource(_resource())

    stored = fixture.records[("core.resources", "r1")]
    assert stored["value"]["resource_id"] == "r1"
    assert stored["value"]["owner"] == "alice"
    assert stored["owner"] == "system"
    assert ("PUT", "/api/v1/records") in [
        (method, path.split("?")[0]) for method, path in fixture.paths
    ]
    assert not any(
        "/resources" in path or "/clear" in path for _method, path in fixture.paths
    )

    fetched = adapter.fetch_resource("r1")
    assert fetched is not None
    assert fetched.owner == "alice"
    assert [r.resource_id for r in adapter.list_resources()] == ["r1"]


def test_adapter_maps_runtimes_and_devices(fixture):
    adapter = _adapter(fixture)
    adapter.persist_runtime(
        RuntimeRecord(entity_id="agent-1", entity_type="agent", status="running")
    )
    assert [r.entity_id for r in adapter.list_runtimes()] == ["agent-1"]
    assert (
        fixture.records[("core.runtimes", "agent-1")]["value"]["entity_type"]
        == "agent"
    )

    adapter.persist_device({"device_id": "dev-1", "name": "Device 1"})
    assert adapter.fetch_device("dev-1")["name"] == "Device 1"
    assert adapter.list_devices() == [{"device_id": "dev-1", "name": "Device 1"}]
    assert ("core.devices", "dev-1") in fixture.records

    adapter.delete_device("dev-1")
    assert adapter.fetch_device("dev-1") is None


def test_adapter_write_failure_is_not_success(fixture):
    adapter = _adapter(fixture, suffix="/missing")
    with pytest.raises(OSError):
        adapter.persist_resource(_resource())
    assert adapter.health()["last_durable_success"] is False


def test_adapter_fallback_still_works_for_failed_writes(fixture):
    adapter = _adapter(fixture, fallback=True, suffix="/missing")
    adapter.persist_resource(_resource(resource_id="fallback"))
    assert adapter.fetch_resource("fallback").resource_id == "fallback"
    assert adapter.health()["healthy"] is False


def test_adapter_health_is_truthful(fixture):
    adapter = _adapter(fixture)
    assert adapter.health()["healthy"] is True
    assert adapter.health()["status"] == "ok"

    fixture.fail_mode = "error"
    health = adapter.health()
    assert health["healthy"] is False
    assert "error" in health
    assert health["last_durable_success"] is False


def test_adapter_clear_only_removes_core_namespaces(fixture):
    adapter = _adapter(fixture)
    adapter.persist_resource(_resource())
    adapter.persist_runtime(RuntimeRecord(entity_id="e1", entity_type="agent"))
    adapter.persist_device({"device_id": "d1"})
    fixture.new_record("foreign.space", "keep", {"v": 1}, {}, "system")

    adapter.clear()

    assert ("foreign.space", "keep") in fixture.records
    assert ("core.memory", "flight-plan") in fixture.records
    assert not any(
        namespace.startswith(("core.resources", "core.runtimes", "core.devices"))
        for namespace, _key in fixture.records
    )
    assert not any("/clear" in path for _method, path in fixture.paths)


def test_reader_requires_api_key(fixture):
    reader = HttpDataReader(
        endpoint=fixture.url, owner_scope="device-a", timeout=2.0
    )
    with pytest.raises(DataAccessDenied):
        reader.list_records("core.memory")


def test_reader_returns_all_101_records(fixture):
    for index in range(101):
        fixture.new_record(
            "core.bulk",
            f"item-{index:03d}",
            {"index": index},
            {},
            "device-a",
        )
    records = _reader(fixture).list_records("core.bulk")
    assert len(records) == 101
    assert {record["key"] for record in records} == {
        f"item-{index:03d}" for index in range(101)
    }


def test_reader_crosses_a_500_item_page(fixture):
    for index in range(501):
        fixture.new_record(
            "core.page",
            f"item-{index:03d}",
            {"index": index},
            {},
            "device-a",
        )
    reader = _reader(fixture)
    records = reader.list_records("core.page")
    assert len(records) == 501

    paths = [
        path
        for method, path in fixture.paths
        if method == "GET" and "namespace=core.page" in path
    ]
    assert any("limit=500" in path and "offset=0" in path for path in paths)
    assert any("offset=500" in path for path in paths)

    tail = reader.list_records("core.page", limit=1, offset=500)
    assert [record["key"] for record in tail] == ["item-500"]


def test_reader_search_uses_query_mode_and_paginates(fixture):
    for index in range(101):
        fixture.new_record(
            "core.search",
            f"needle-{index:03d}",
            {"topic": "needle"},
            {},
            "device-a",
        )
    reader = _reader(fixture)
    found = reader.search_records("needle", "core.search")
    assert len(found) == 101
    assert not any("/api/v1/records/search" in path for _m, path in fixture.paths)
    assert any("query=needle" in path for _m, path in fixture.paths)


def test_reader_get_record_exact_key_after_prefix_pages(fixture):
    for index in range(101):
        fixture.new_record(
            "core.lookup",
            f"target-{index:03d}",
            {"index": index},
            {},
            "device-a",
        )
    fixture.new_record("core.lookup", "target", {"exact": True}, {}, "device-a")
    record = _reader(fixture).get_record("core.lookup", "target")
    assert record["value"] == {"exact": True}
