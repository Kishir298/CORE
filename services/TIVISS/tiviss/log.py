"""Structured logging for T.I.V.I.S.S.

Stdlib :mod:`logging` with JSON-lines records carrying timestamp, agent,
component, request, event, outcome, and error fields. Values under
secret-looking keys (token, secret, password, api_key, credential) are
redacted before emission — secrets must never reach logs.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, TextIO

_SECRET_HINTS = ("token", "secret", "password", "api_key", "apikey", "credential")
REDACTED = "***redacted***"


def redact(value: Any) -> Any:
    """Recursively replace secret-looking mapping values with a marker."""
    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(hint in lowered for hint in _SECRET_HINTS):
                cleaned[key] = REDACTED
            else:
                cleaned[key] = redact(item)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        details = getattr(record, "details", None)
        if isinstance(details, Mapping):
            payload["details"] = redact(dict(details))
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def get_logger(
    name: str = "tiviss",
    *,
    level: int = logging.INFO,
    stream: TextIO | None = None,
) -> logging.Logger:
    """Return a JSON-lines logger (no duplicate handlers on repeat calls)."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    for handler in logger.handlers:
        if getattr(handler, "_tiviss_json", False):
            handler.setLevel(level)
            return logger
    handler = logging.StreamHandler(stream or io.StringIO())
    handler._tiviss_json = True  # type: ignore[attr-defined]
    handler.setLevel(level)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    return logger


def log_event(
    logger: logging.Logger,
    *,
    event: str,
    agent_id: str = "",
    component: str = "",
    request_id: str = "",
    outcome: str = "",
    error: str = "",
    details: Mapping[str, Any] | None = None,
    level: int = logging.INFO,
) -> None:
    """Emit one structured event record with secret redaction."""
    record_details: dict[str, Any] = {
        "event": event,
        "agent_id": agent_id,
        "component": component,
        "request_id": request_id,
        "outcome": outcome,
    }
    if error:
        record_details["error"] = error
    if details:
        record_details.update(details)
    logger.log(level, event, extra={"details": record_details})


def read_records(stream: io.StringIO) -> list[dict[str, Any]]:
    """Parse JSON-lines back (test/helper use)."""
    out = []
    for line in stream.getvalue().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out
