"""
C.O.R.E. adapter errors for A.S.I.S.

All failures crossing the A.S.I.S. ↔ C.O.R.E. boundary surface as one of
these structured errors. Raw transport tracebacks and credentials never
propagate to the model, memory, or logs.
"""

from __future__ import annotations


class CoreError(Exception):
    """Base error for C.O.R.E. integration failures."""

    def __init__(self, message: str, *, code: str = "CORE_ERROR") -> None:
        super().__init__(message)
        self.code = code


class CoreUnavailable(CoreError):
    """C.O.R.E. is disabled, unreachable, or the client package is missing."""

    def __init__(self, message: str = "C.O.R.E. is unavailable.") -> None:
        super().__init__(message, code="CORE_UNAVAILABLE")


class CoreTimeout(CoreError):
    """A C.O.R.E. request exceeded its bounded timeout."""

    def __init__(self, message: str = "C.O.R.E. request timed out.") -> None:
        super().__init__(message, code="CORE_TIMEOUT")


class CoreAuthError(CoreError):
    """Authentication/session failure (expired token, rejected credential)."""

    def __init__(self, message: str = "C.O.R.E. authentication failed.") -> None:
        super().__init__(message, code="CORE_AUTH_ERROR")


class CoreProtocolError(CoreError):
    """Malformed, oversized, or unexpected host response."""

    def __init__(self, message: str = "C.O.R.E. protocol error.") -> None:
        super().__init__(message, code="CORE_PROTOCOL_ERROR")
