"""Contract endpoint and integration-contract tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from rescs.contract import CAPABILITIES


def test_contract_requires_api_key(client: TestClient):
    response = client.get("/api/v1/contract", headers={"X-API-Key": ""})
    assert response.status_code == 401


def test_contract_describes_capabilities(client: TestClient):
    response = client.get("/api/v1/contract")
    assert response.status_code == 200
    contract = response.json()
    assert contract["api_version"] == "v1"
    assert contract["auth"]["header"] == "X-API-Key"
    assert contract["pagination"] == {
        "limit_min": 1,
        "limit_max": 500,
        "limit_default": 100,
    }
    assert contract["reserved_namespaces"] == [
        "core.",
        "rescs.",
        "asis.",
        "tiviss.",
        "personal.",
    ]
    assert contract["endpoints"]["records"] == "/api/v1/records"
    assert contract["owner"]["default"] == "system"
    assert contract["owner"]["locked"] is False


def test_contract_matches_capability_module(client: TestClient):
    contract = client.get("/api/v1/contract").json()
    assert contract["capabilities"] == CAPABILITIES


def test_contract_locks_owner_when_configured(scoped_client: TestClient):
    contract = scoped_client.get("/api/v1/contract").json()
    assert contract["owner"]["locked"] is True
    assert contract["owner"]["locked_to"] == "tenant-a"
