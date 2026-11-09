"""RESCS application factory and HTTP entry point.

Wires configuration, logging, database, service layer, health probes,
exception handlers and the versioned HTTP API.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from rescs.api import API_VERSION
from rescs.api.deps import register_health_checks
from rescs.api.errors import register_exception_handlers
from rescs.api.routers import admin, contract, files, health, records, uploads
from rescs.config import Settings, get_settings
from rescs.db.bootstrap import Database, bootstrap_database
from rescs.health import HealthService
from rescs.logging import configure_logging, get_logger
from rescs.observability import ObservabilityMiddleware
from rescs.services.factory import Services, build_services

logger = get_logger(__name__)


def create_app(
    settings: Settings | None = None,
) -> FastAPI:
    """Build a fully configured RESCS FastAPI application."""
    if settings is None:
        settings = get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info(
            "starting %s v%s (%s)",
            settings.app_name,
            settings.version,
            settings.environment,
        )
        from rescs.mounts import check_mount
        check_mount(settings)
        database: Database = bootstrap_database(settings)
        services: Services = build_services(
            database=database,
            storage_dir=settings.storage_dir,
            settings=settings,
        )
        app.state.database = database
        app.state.services = services
        register_health_checks(app)
        logger.info(
            "connected to %s database, schema %s",
            database.backend,
            database.schema_version or "n/a",
        )
        try:
            yield
        finally:
            database.engine.dispose()
            logger.info("%s stopped", settings.app_name)

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="Rishik's Efficient System for Cloud Storage",
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.health = HealthService()

    # NOTE: Starlette runs middleware in reverse order of registration,
    # so RateLimit is registered first (inner) and Observability second
    # (outer). Every response — including 429s short-circuited by the
    # limiter — therefore carries X-Request-ID correlation.
    from rescs.rate_limit import RateLimitMiddleware

    app.add_middleware(RateLimitMiddleware, settings=settings)
    app.add_middleware(
        ObservabilityMiddleware,
        settings=settings,
    )

    from rescs.gateway_scope import ScopeMiddleware
    app.add_middleware(ScopeMiddleware, settings=settings)
    register_exception_handlers(app)

    @app.get("/", tags=["meta"])
    def root() -> dict[str, Any]:
        return {
            "service": settings.app_name,
            "version": settings.version,
            "api_version": API_VERSION,
            "docs": "/docs",
        }

    app.include_router(health.router)
    app.include_router(admin.router, prefix=f"/api/{API_VERSION}")
    app.include_router(contract.router, prefix=f"/api/{API_VERSION}")
    app.include_router(records.router, prefix=f"/api/{API_VERSION}")
    app.include_router(files.router, prefix=f"/api/{API_VERSION}")
    app.include_router(uploads.router, prefix=f"/api/{API_VERSION}")

    return app
