"""T.I.V.I.S.S. error definitions.

Structured error codes and exceptions for consistent error handling.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Standardized error codes."""

    # Configuration
    CONFIG_INVALID = "CONFIG_INVALID"
    CONFIG_MISSING = "CONFIG_MISSING"

    # Web
    WEB_DISABLED = "WEB_DISABLED"
    WEB_INVALID_URL = "WEB_INVALID_URL"
    WEB_UNSUPPORTED_SCHEME = "WEB_UNSUPPORTED_SCHEME"
    WEB_PROVIDER_ERROR = "WEB_PROVIDER_ERROR"
    WEB_TIMEOUT = "WEB_TIMEOUT"
    WEB_REDIRECT_LOOP = "WEB_REDIRECT_LOOP"
    WEB_RESPONSE_TOO_LARGE = "WEB_RESPONSE_TOO_LARGE"
    WEB_PRIVATE_ADDRESS = "WEB_PRIVATE_ADDRESS"

    # Translation
    TRANSLATION_DISABLED = "TRANSLATION_DISABLED"
    TRANSLATION_PROVIDER_ERROR = "TRANSLATION_PROVIDER_ERROR"
    TRANSLATION_MODEL_ERROR = "TRANSLATION_MODEL_ERROR"

    # Voice
    VOICE_DISABLED = "VOICE_DISABLED"
    VOICE_PROVIDER_ERROR = "VOICE_PROVIDER_ERROR"
    VOICE_NOT_INITIALIZED = "VOICE_NOT_INITIALIZED"

    # Calculator
    CALCULATION_DISABLED = "CALCULATION_DISABLED"
    CALCULATION_PROVIDER_ERROR = "CALCULATION_PROVIDER_ERROR"
    CALCULATION_SYNTAX_ERROR = "CALCULATION_SYNTAX_ERROR"

    # Memory
    MEMORY_KEY_ERROR = "MEMORY_KEY_ERROR"
    MEMORY_BACKEND_ERROR = "MEMORY_BACKEND_ERROR"
    MEMORY_SERIALIZATION_ERROR = "MEMORY_SERIALIZATION_ERROR"

    # ASCS
    ASCS_DISABLED = "ASCS_DISABLED"
    ASCS_EXECUTION_ERROR = "ASCS_EXECUTION_ERROR"
    ASCS_HANDOVER_ERROR = "ASCS_HANDOVER_ERROR"

    # Generic
    INTERNAL_ERROR = "INTERNAL_ERROR"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    VALIDATION_ERROR = "VALIDATION_ERROR"


class TivissError(Exception):
    """Base exception for TIVISS errors with error code."""

    def __init__(self, code: ErrorCode | str, message: str, details: dict[str, Any] | None = None):
        self.code = ErrorCode(code) if isinstance(code, str) else code
        self.message = message
        self.details = details or {}
        super().__init__(f"{self.code}: {message}")


class ConfigValidationError(TivissError):
    """Raised when configuration validation fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(ErrorCode.CONFIG_INVALID, message, details)


class MemoryKeyError(TivissError):
    """Raised when a memory key is not found."""

    def __init__(self, key: str, details: dict[str, Any] | None = None):
        super().__init__(ErrorCode.MEMORY_KEY_ERROR, f"Memory key not found: {key}", details)


class ToolError(TivissError):
    """Raised for tool input validation failures."""

    def __init__(self, message: str, code: ErrorCode = ErrorCode.VALIDATION_ERROR, details: dict[str, Any] | None = None):
        super().__init__(code, message, details)