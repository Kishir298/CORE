"""
C.O.R.E. protocol helpers for A.S.I.S.

Envelope validation, secret redaction, and bounded result normalization so
host responses can never leak credentials into prompts/memory/logs nor blow
up the model context window.
"""

from __future__ import annotations

import json
from typing import Any

#: Payload keys that must never reach the model, memory, logs, or disk.
REDACTED_KEYS = frozenset(
    {
        "token",
        "credential",
        "password",
        "api_token",
        "session",
        "session_token",
        "_session_token",
        "connection_id",
        "authenticated",
    }
)

#: Hard ceiling for any single tool-facing payload serialized as JSON.
MAX_RESULT_CHARS = 8_000

REDACTED = "***REDACTED***"


def redact(value: Any) -> Any:
    """Recursively replace secret-bearing keys with a placeholder."""
    if isinstance(value, dict):
        return {
            key: (REDACTED if key in REDACTED_KEYS else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        cleaned = [redact(item) for item in value]
        return type(value)(cleaned) if isinstance(value, tuple) else cleaned
    return value


def contains_secret_keys(value: Any) -> bool:
    """Return True if any secret-bearing key is present (for tests/guards)."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in REDACTED_KEYS:
                return True
            if contains_secret_keys(item):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(contains_secret_keys(item) for item in value)
    return False


def normalize_result(data: Any, max_chars: int = MAX_RESULT_CHARS) -> Any:
    """Redact then bound the size of a host response for model consumption."""
    cleaned = redact(data)
    try:
        text = json.dumps(cleaned, default=str)
    except Exception:
        text = str(cleaned)
    if len(text) <= max_chars:
        return cleaned
    truncated = text[:max_chars]
    return {"truncated": True, "max_chars": max_chars, "preview": truncated}


def validate_envelope(message: Any) -> dict[str, Any]:
    """Validate a host response envelope; raise CoreProtocolError if bad."""
    from .errors import CoreProtocolError

    if not isinstance(message, dict):
        raise CoreProtocolError("Host response must be a mapping.")
    for field in ("message_type", "payload"):
        if field not in message:
            raise CoreProtocolError(f"Host response missing {field!r}.")
    if not isinstance(message["message_type"], str) or not message["message_type"]:
        raise CoreProtocolError("Host response has an invalid message_type.")
    if not isinstance(message["payload"], dict):
        raise CoreProtocolError("Host response payload must be a mapping.")
    return message


def error_message(exc: BaseException) -> str:
    """Map raw transport errors to stable, secret-free tool messages."""
    from .errors import CoreError

    if isinstance(exc, CoreError):
        return f"{exc.code}: {exc}"
    name = type(exc).__name__
    if "timeout" in name.lower() or "timed out" in str(exc).lower():
        return f"CORE_TIMEOUT: {exc}"
    return f"CORE_UNAVAILABLE: {exc}"
