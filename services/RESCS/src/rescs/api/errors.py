"""Consistent API error responses."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from rescs.errors import RESCSError
from rescs.logging import get_logger

logger = get_logger(__name__)

_STATUS_TO_CODE = {
    400: "INVALID_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    412: "PRECONDITION_FAILED",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    500: "INTERNAL_ERROR",
    503: "DEPENDENCY_UNAVAILABLE",
}


def _loc_to_string(loc: list) -> str:
    return ".".join(str(part) for part in loc)


def _validation_detail(exc: RequestValidationError) -> list[dict]:
    detail = []
    for error in exc.errors():
        detail.append(
            {
                "loc": _loc_to_string(error.get("loc", [])),
                "message": error.get("msg"),
                "type": error.get("type"),
            }
        )
    return detail


def _request_id_headers(request: Request) -> dict[str, str]:
    """Fallback request-ID propagation for paths bypassing middleware send."""
    request_id: str | None = None
    header_name = "X-Request-ID"
    try:
        from rescs.observability import request_id_var

        request_id = request_id_var.get()
    except Exception:
        request_id = None
    try:
        scope = getattr(request, "scope", {}) or {}
        if not request_id:
            scope_rid = scope.get("rescs.request_id")
            if isinstance(scope_rid, str) and scope_rid:
                request_id = scope_rid
        scope_header = scope.get("rescs.request_id_header")
        if isinstance(scope_header, str) and scope_header:
            header_name = scope_header
        else:
            try:
                settings_header = request.app.state.settings.request_id_header
                if settings_header:
                    header_name = settings_header
            except Exception:
                pass
    except Exception:
        pass
    if not request_id:
        return {}
    return {header_name: request_id}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RESCSError)
    async def _rescs_error_handler(request: Request, exc: RESCSError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.to_dict()},
            headers=_request_id_headers(request),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "request validation failed",
                    "details": {"errors": _validation_detail(exc)},
                }
            },
            headers=_request_id_headers(request),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = _STATUS_TO_CODE.get(exc.status_code)
        if code is None:
            code = "INTERNAL_ERROR" if exc.status_code >= 500 else "INVALID_REQUEST"
        # Never echo raw internals; use the safe HTTP reason when available.
        message = str(exc.detail) if isinstance(exc.detail, str) else code.lower()
        # Starlette defaults like "Not Found" are safe; anything else is
        # collapsed to a generic message to avoid leaking internals.
        safe_messages = {
            400: "bad request",
            401: "unauthorized",
            403: "forbidden",
            404: "not found",
            405: "method not allowed",
            409: "conflict",
            412: "precondition failed",
            413: "payload too large",
            422: "validation error",
            500: "internal server error",
            503: "service unavailable",
        }
        message = safe_messages.get(exc.status_code, message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": code, "message": message, "details": None}},
            headers=_request_id_headers(request),
        )

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled application error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "internal server error",
                    "details": None,
                }
            },
            headers=_request_id_headers(request),
        )
