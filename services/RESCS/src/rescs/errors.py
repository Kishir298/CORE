"""Domain error foundation for RESCS.

All RESCS-specific failures raise :class:`RESCSError` (or a subclass).
Each error carries a stable machine-readable ``code``, an HTTP ``status_code``,
and optional structured ``details``. Raw database/storage exceptions are never
exposed to API consumers directly.
"""

from __future__ import annotations

from typing import Any


class RESCSError(Exception):
    """Base class for all RESCS domain errors."""

    code = "INTERNAL_ERROR"
    status_code = 500

    def __init__(self, message: str | None = None, *, details: Any = None) -> None:
        self.message = message or self.__class__.__name__
        self.details = details
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class ConfigurationError(RESCSError):
    code = "CONFIGURATION_ERROR"
    status_code = 500


class InvalidRequestError(RESCSError):
    code = "INVALID_REQUEST"
    status_code = 400


class UnauthorizedError(RESCSError):
    code = "UNAUTHORIZED"
    status_code = 401


class ForbiddenError(RESCSError):
    code = "FORBIDDEN"
    status_code = 403


class NotFoundError(RESCSError):
    code = "NOT_FOUND"
    status_code = 404


class ConflictError(RESCSError):
    code = "CONFLICT"
    status_code = 409


class PreconditionFailedError(RESCSError):
    code = "PRECONDITION_FAILED"
    status_code = 412


class UnprocessableContentError(RESCSError):
    """Legacy alias of VALIDATION_ERROR (422); prefer VALIDATION_ERROR."""

    code = "UNPROCESSABLE_CONTENT"
    status_code = 422


class StorageError(RESCSError):
    code = "STORAGE_ERROR"
    status_code = 500


class PayloadTooLargeError(RESCSError):
    code = "PAYLOAD_TOO_LARGE"
    status_code = 413


class QuotaExceededError(RESCSError):
    code = "QUOTA_EXCEEDED"
    status_code = 403


class DependencyUnavailableError(RESCSError):
    code = "DEPENDENCY_UNAVAILABLE"
    status_code = 503
