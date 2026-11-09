"""API: rate limiting (429 + headers, health exempt)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from rescs.config import Settings
from rescs.main import create_app


def _limited_client(**overrides):
    base = dict(
        api_key="rate-limit-key-0123456789abcdef",
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        storage_dir="rescs_test_storage",
        rate_limit_enabled=True,
        rate_limit_general_per_minute=2,
        rate_limit_writes_per_minute=2,
        rate_limit_uploads_per_minute=2,
        _env_file=None,
    )
    base.update(overrides)
    settings = Settings(**base)
    app = create_app(settings=settings)
    return TestClient(app, headers={"X-API-Key": settings.api_key})


def test_rate_limit_general_429():
    with _limited_client() as client:
        assert client.get("/api/v1/records").status_code == 200
        assert client.get("/api/v1/records").status_code == 200
        r = client.get("/api/v1/records")
        assert r.status_code == 429
        assert r.json()["error"]["code"] == "RATE_LIMITED"
        assert "Retry-After" in r.headers


def test_rate_limit_health_exempt():
    with _limited_client(rate_limit_general_per_minute=1) as client:
        client.get("/api/v1/records")
        assert client.get("/api/v1/records").status_code == 429
        # Health never limited.
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code in (200, 503)


def test_rate_limit_429_carries_request_id():
    with _limited_client(rate_limit_general_per_minute=1) as client:
        client.get("/api/v1/records")
        r = client.get("/api/v1/records")
        assert r.status_code == 429
        assert r.headers.get("X-Request-ID")


def test_rate_limit_map_bounded_on_new_keys():
    from rescs.rate_limit import MAX_TRACKED_KEYS, RateLimitMiddleware

    with _limited_client(
        rate_limit_general_per_minute=10**9,
        rate_limit_writes_per_minute=10**9,
        rate_limit_uploads_per_minute=10**9,
    ) as client:
        # One request first: Starlette builds middleware_stack lazily.
        client.get("/api/v1/records")
        # Reach the middleware through the app stack.
        node = client.app.middleware_stack
        while node is not None and not isinstance(node, RateLimitMiddleware):
            node = getattr(node, "app", None)
        middleware = node
        assert middleware is not None
        for i in range(MAX_TRACKED_KEYS + 50):
            client.get("/api/v1/records", headers={"X-API-Key": f"key-{i:06d}"})
        assert len(middleware._hits) <= MAX_TRACKED_KEYS

