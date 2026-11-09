"""R.E.S.C.S. integration adapter tests (local mock transport, no external deps)."""

import pytest

from tiviss.integrations import IntegrationStatus, LocalRESCSAdapter
from tiviss.memory import MemoryRecord


@pytest.fixture
def rescs():
    return LocalRESCSAdapter()


def test_rescs_connect_requires_authorization(rescs):
    assert rescs.connect(authorized=False) is False
    assert rescs.connected() is False


def test_rescs_put_and_get(rescs):
    rescs.connect(authorized=True)
    put = rescs.put(MemoryRecord(key="fact", content="hello"))
    assert put.ok
    got = rescs.get(put.payload["record_id"])
    assert got.ok
    assert got.payload["content"] == "hello"


def test_rescs_search(rescs):
    rescs.connect(authorized=True)
    rescs.put(MemoryRecord(key="a", content="alpha beta"))
    rescs.put(MemoryRecord(key="b", content="gamma beta"))
    result = rescs.search("beta")
    assert result.ok
    assert result.payload["total"] == 2


def test_rescs_get_missing_record(rescs):
    rescs.connect(authorized=True)
    response = rescs.get("missing")
    assert response.ok is False
    assert "not found" in response.error


def test_rescs_clear(rescs):
    rescs.connect(authorized=True)
    put = rescs.put(MemoryRecord(key="k", content="v"))
    assert len(rescs.backend) == 1
    rescs.clear()
    assert len(rescs.backend) == 0
    assert put.ok


def test_rescs_disconnected_is_unavailable(rescs):
    response = rescs.put(MemoryRecord(key="k", content="v"))
    assert response.status is IntegrationStatus.NOT_AVAILABLE


def test_rescs_failure_mode(rescs):
    rescs.connect(authorized=True)
    rescs._failure_mode = True
    response = rescs.put(MemoryRecord(key="k", content="v"))
    assert response.status is IntegrationStatus.ERROR


def test_rescs_interactions_recorded(rescs):
    rescs.connect(authorized=True)
    rescs.put(MemoryRecord(key="k", content="v"))
    rescs.get("k")
    assert len(rescs.interactions) == 2
    assert [i.operation for i in rescs.interactions] == ["put", "get"]


def test_rescs_health(rescs):
    rescs.connect(authorized=True)
    rescs.put(MemoryRecord(key="k", content="v"))
    health = rescs.health()
    assert health["adapter"] == "rescs.local"
    assert health["stored_records"] == 1
