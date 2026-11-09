"""Observability: request correlation ids and access logging."""

from __future__ import annotations

import re
import time
import uuid
from contextvars import ContextVar

from rescs.config import Settings
from rescs.logging import get_logger

logger = get_logger("rescs.access")

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def make_request_id(header_value: str | None, settings: Settings) -> str:
    """Honour a caller-supplied tracing id, otherwise mint one."""
    if header_value:
        value = header_value.strip()
        if _SAFE_REQUEST_ID.match(value):
            return value
    return uuid.uuid4().hex


def _with_request_id_header(
    headers_raw: list[tuple[bytes, bytes]],
    request_id: str,
    header_name: str,
) -> list[tuple[bytes, bytes]]:
    key = header_name.encode("latin-1").lower()
    for existing_key, _ in headers_raw:
        if existing_key.lower() == key:
            return headers_raw
    return headers_raw + [
        (header_name.encode("latin-1"), request_id.encode("latin-1"))
    ]


class ObservabilityMiddleware:
    """ASGI middleware that correlates, times and logs HTTP requests."""

    def __init__(self, app, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        header_name = self.settings.request_id_header or "X-Request-ID"
        incoming = {
            k.decode("latin-1").lower(): v.decode("latin-1", "replace")
            for k, v in (scope.get("headers") or [])
        }.get(header_name.lower())

        request_id = make_request_id(incoming, self.settings)
        status_code = 500
        started = time.perf_counter()
        token = request_id_var.set(request_id)
        # Stash on the ASGI scope so ServerErrorMiddleware handlers (which run
        # outside this middleware for generic Exception) can still propagate
        # the correlation id even after the ContextVar is reset.
        try:
            scope["rescs.request_id"] = request_id
            scope["rescs.request_id_header"] = header_name
        except Exception:
            pass

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message["headers"] = _with_request_id_header(
                    message.get("headers", []), request_id, header_name
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "http_request request_id=%s method=%s path=%s status=%d "
                "duration_ms=%.1f",
                request_id,
                scope.get("method", ""),
                scope.get("path", ""),
                status_code,
                duration_ms,
            )
            request_id_var.reset(token)
