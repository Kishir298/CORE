"""API dependencies and health-check wiring."""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Request

from rescs.config import Settings
from rescs.db.engine import check_connectivity
from rescs.logging import get_logger
from rescs.services.factory import Services

logger = get_logger(__name__)


def get_settings(request: Request) -> Settings:
    return getattr(request.state, "scoped_settings", request.app.state.settings)


def get_services(request: Request) -> Services:
    return request.app.state.services


def parse_etag(header_value: str | None) -> str | None:
    """Extract an entity tag from an ``If-Match`` style header value.

    Accepts a bare entity tag (our canonical form) or the RFC 9110 quoted/
    weak form. ``*`` and empty values map to ``None``.
    """
    if not header_value:
        return None
    value = header_value.strip()
    if value == "*":
        return None
    if value.startswith("W/"):
        value = value[2:].strip()
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        return value[1:-1]
    return value


PROBE_KEY = "_rescs_probe"


def _database_check(app: FastAPI) -> str:
    try:
        check_connectivity(app.state.database.engine)
        return "ok"
    except Exception:
        return "down"


def _storage_check(app: FastAPI) -> str:
    probe = f"{PROBE_KEY}_{uuid.uuid4().hex}"
    try:
        store = app.state.services.files.object_store
        store.put(probe, b"ok")
        try:
            healthy = store.get(probe) == b"ok"
        finally:
            try:
                store.delete(probe)
            except Exception:
                pass
        return "ok" if healthy else "down"
    except Exception:
        try:
            app.state.services.files.object_store.delete(probe)
        except Exception:
            pass
        return "down"


def register_health_checks(app: FastAPI) -> None:
    """Register real dependency probes against the live app state."""
    if hasattr(app.state, "database"):
        app.state.health.register("database", lambda: _database_check(app))
    app.state.health.register("storage", lambda: _storage_check(app))
