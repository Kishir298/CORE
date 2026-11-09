"""Health endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/health/live")
def health_live(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    return {
        "status": "alive",
        "service": settings.app_name,
        "version": settings.version,
    }


@router.get("/health/ready")
def health_ready(request: Request) -> JSONResponse:
    report = request.app.state.health.report()
    ready = report["status"] == "ok"
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ready" if ready else "not_ready",
            "checks": report["checks"],
        },
    )


@router.get("/health")
def health_summary(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    report = request.app.state.health.report()
    healthy = report["status"] == "ok"
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "service": settings.app_name,
            "version": settings.version,
            **report,
        },
    )
