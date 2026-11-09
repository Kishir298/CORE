"""Observability middleware tests: request correlation ids and propagation."""

from __future__ import annotations

from fastapi.testclient import TestClient

from rescs.main import create_app


def test_generates_request_id_when_none_supplied(settings):
    app = create_app(settings=settings)
    with TestClient(app, headers={"X-API-Key": settings.api_key}) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id
    assert len(request_id) > 0


def test_honours_caller_supplied_request_id(settings):
    app = create_app(settings=settings)
    supplied = "trace-abc-12345"
    with TestClient(
        app,
        headers={"X-API-Key": settings.api_key, "X-Request-ID": supplied},
    ) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == supplied


def test_overlong_request_id_falls_back_to_generated(settings):
    app = create_app(settings=settings)
    overlong = "x" * 200
    with TestClient(
        app,
        headers={"X-API-Key": settings.api_key, "X-Request-ID": overlong},
    ) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id
    assert request_id != overlong


def test_response_carries_request_id_on_errors(settings):
    app = create_app(settings=settings)
    with TestClient(
        app,
        headers={"X-API-Key": settings.api_key, "X-Request-ID": "err-trace-1"},
    ) as client:
        response = client.get("/api/v1/records/does-not-exist")

    assert "X-Request-ID" in response.headers
    assert response.headers["X-Request-ID"] == "err-trace-1"


def test_non_http_scope_passes_through():
    import asyncio

    from rescs.config import Settings
    from rescs.observability import ObservabilityMiddleware

    settings = Settings(_env_file=None)
    marker = {"called": False}

    async def inner_app(scope, receive, send):
        marker["called"] = True

    middleware = ObservabilityMiddleware(inner_app, settings)

    async def pump():
        async def receive():
            return {"type": "lifespan.startup", "message": ""}

        async def send(message):
            pass

        await middleware({"type": "lifespan"}, receive, send)

    asyncio.run(pump())
    assert marker["called"] is True

