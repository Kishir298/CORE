"""Phase 10 readiness failure-matrix tests.

Covers liveness vs readiness, dependency failure → 503, exception safety,
secret-leakage, public health policy and request-ID propagation.
Uses only in-process fault injection (no external database).
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from rescs.main import create_app


def _body_text(response) -> str:
    return json.dumps(response.json(), default=str).lower()


def _assert_no_secrets(response, settings) -> None:
    text = _body_text(response)
    # API key must never appear in a health body.
    assert settings.api_key not in text
    for token in ("password", "secret", "authorization", "x-api-key", "traceback"):
        assert token not in text
    # Database URL (which may embed credentials) must not be dumped.
    db_url = (settings.database_url or "").lower()
    if db_url and len(db_url) > 8:
        # Compare a distinctive fragment rather than the full sqlite memory URL
        # which is trivially "sqlite..."; still guard postgres-style URLs.
        if "://" in db_url and not db_url.startswith("sqlite"):
            assert db_url not in text


def test_liveness_shape_and_no_dependency_requirement(client: TestClient):
    response = client.get("/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "alive"
    assert body["service"] == "RESCS"
    assert "version" in body
    assert "X-Request-ID" in response.headers


def test_readiness_healthy(client: TestClient, settings):
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["storage"] == "ok"
    assert "X-Request-ID" in response.headers
    _assert_no_secrets(response, settings)


def test_readiness_database_failure_reports_503(client: TestClient, settings):
    client.app.state.health.register("database", lambda: "down")
    response = client.get("/health/ready", headers={"X-Request-ID": "ready-db-fail-1"})
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"] == "down"
    assert response.headers.get("X-Request-ID") == "ready-db-fail-1"
    _assert_no_secrets(response, settings)


def test_readiness_storage_failure_reports_503(client: TestClient, settings):
    client.app.state.health.register("storage", lambda: "down")
    response = client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["storage"] == "down"
    assert "X-Request-ID" in response.headers
    _assert_no_secrets(response, settings)


def test_readiness_multiple_failures_aggregate(client: TestClient):
    client.app.state.health.register("database", lambda: "down")
    client.app.state.health.register("storage", lambda: "down")
    response = client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"] == {"database": "down", "storage": "down"}


def test_readiness_check_exception_is_safe_failure(client: TestClient, settings):
    def boom() -> str:
        raise RuntimeError("connection exploded SELECT * FROM records")

    client.app.state.health.register("database", boom)
    response = client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["checks"]["database"] == "down"
    text = _body_text(response)
    assert "traceback" not in text
    assert "exploded" not in text
    assert "select" not in text
    _assert_no_secrets(response, settings)


def test_readiness_degraded_reports_503(client: TestClient):
    client.app.state.health.register("storage", lambda: "degraded")
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_health_summary_failure_reports_503(client: TestClient, settings):
    client.app.state.health.register("database", lambda: "down")
    response = client.get("/health", headers={"X-Request-ID": "summary-fail-1"})
    assert response.status_code == 503
    body = response.json()
    assert body["checks"]["database"] == "down"
    assert response.headers.get("X-Request-ID") == "summary-fail-1"
    _assert_no_secrets(response, settings)


def test_health_endpoints_are_public(settings):
    app = create_app(settings=settings)
    with TestClient(app) as anon:
        assert anon.get("/health/live").status_code == 200
        assert anon.get("/health/ready").status_code == 200
        assert anon.get("/health").status_code == 200
        # Authenticated surface still guarded.
        denied = anon.get("/api/v1/records")
        assert denied.status_code in (401, 403)


def test_unknown_route_returns_envelope_with_request_id(settings):
    app = create_app(settings=settings)
    with TestClient(app, headers={"X-API-Key": settings.api_key}) as api:
        response = api.get("/no-such-route-xyz", headers={"X-Request-ID": "unknown-1"})
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert response.headers.get("X-Request-ID") == "unknown-1"
    _assert_no_secrets(response, settings)


def test_unhandled_exception_returns_safe_envelope_with_request_id(settings):
    app = create_app(settings=settings)

    @app.get("/_boom_for_test")
    def _boom():
        raise RuntimeError("super secret db password=hunter2")

    with TestClient(app, raise_server_exceptions=False) as api:
        response = api.get("/_boom_for_test", headers={"X-Request-ID": "boom-1"})
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    text = _body_text(response)
    assert "hunter2" not in text
    assert "traceback" not in text
    assert response.headers.get("X-Request-ID") == "boom-1"

