"""C.O.R.E. device communication protocol constants.

Central definition of the device registration / discovery / presence /
routing protocol so TCP transport, router, application and tests share one
authoritative contract. No networking code lives here.
"""

from __future__ import annotations

# -- message types (exact wire values) ------------------------------------
DEVICE_REGISTER = "DEVICE_REGISTER"
DEVICE_REGISTER_RESPONSE = "DEVICE_REGISTER_RESPONSE"
DEVICE_DISCOVER = "DEVICE_DISCOVER"
DEVICE_DISCOVER_RESPONSE = "DEVICE_DISCOVER_RESPONSE"
DEVICE_INFO = "DEVICE_INFO"
DEVICE_INFO_RESPONSE = "DEVICE_INFO_RESPONSE"
DEVICE_ERROR = "DEVICE_ERROR"

# -- fixed error codes (exact wire values for DEVICE_ERROR.error) ---------
DEVICE_UNAVAILABLE = "DEVICE_UNAVAILABLE"
DEVICE_NOT_FOUND = "DEVICE_NOT_FOUND"
DEVICE_ALREADY_REGISTERED = "DEVICE_ALREADY_REGISTERED"
DEVICE_NOT_REGISTERED = "DEVICE_NOT_REGISTERED"
DEVICE_REGISTRATION_FAILED = "DEVICE_REGISTRATION_FAILED"
INVALID_DESTINATION = "INVALID_DESTINATION"
COMMUNICATION_ERROR = "COMMUNICATION_ERROR"

ERROR_CODES = frozenset(
    {
        DEVICE_ERROR,
        DEVICE_UNAVAILABLE,
        DEVICE_NOT_FOUND,
        DEVICE_ALREADY_REGISTERED,
        DEVICE_NOT_REGISTERED,
        DEVICE_REGISTRATION_FAILED,
        INVALID_DESTINATION,
        COMMUNICATION_ERROR,
    }
)

# -- device presence (only these two values are valid) ---------------------
DEVICE_STATUS_ONLINE = "online"
DEVICE_STATUS_OFFLINE = "offline"

# -- protocol version used by the device registration contract -------------
SUPPORTED_PROTOCOL_VERSION = "0.3.0"

# -- minimum TLS version (TLS 1.2) ------------------------------------------
try:  # pragma: no cover - environment dependent
    import ssl as _ssl

    MINIMUM_TLS_VERSION = _ssl.TLSVersion.TLSv1_2
except Exception:  # pragma: no cover - very old Python
    MINIMUM_TLS_VERSION = "TLSv1.2"

# -- registration payload contract ------------------------------------------
REQUIRED_REGISTRATION_FIELDS = (
    "device_id",
    "device_name",
    "device_type",
    "platform",
    "capabilities",
    "protocol_version",
)


def is_supported_protocol_version(version: str | None) -> bool:
    """Return whether a device protocol version is supported."""
    if not isinstance(version, str) or not version.strip():
        return False
    try:
        from core.version import is_supported as _is_supported

        return bool(_is_supported(version.strip()))
    except Exception:
        return version.strip() == SUPPORTED_PROTOCOL_VERSION


def validate_registration_payload(payload: object) -> tuple[str | None, str | None]:
    """Validate a DEVICE_REGISTER payload.

    Returns ``(None, None)`` when valid, else ``(error_code, message)``.
    Never raises and never synthesizes a device ID.
    """
    if not isinstance(payload, dict):
        return DEVICE_REGISTRATION_FAILED, "Invalid registration payload structure."
    device_id = payload.get("device_id")
    if device_id is None or (isinstance(device_id, str) and device_id == ""):
        if device_id is None:
            return DEVICE_REGISTRATION_FAILED, "Missing device_id."
        return DEVICE_REGISTRATION_FAILED, "Empty device_id."
    if not isinstance(device_id, str):
        return DEVICE_REGISTRATION_FAILED, "Invalid device_id."
    device_name = payload.get("device_name")
    if device_name is None:
        return DEVICE_REGISTRATION_FAILED, "Missing device_name."
    if not isinstance(device_name, str) or device_name == "":
        return DEVICE_REGISTRATION_FAILED, "Empty device_name."
    if payload.get("device_type") is None:
        return DEVICE_REGISTRATION_FAILED, "Missing device_type."
    if payload.get("platform") is None:
        return DEVICE_REGISTRATION_FAILED, "Missing platform."
    if "capabilities" not in payload:
        return DEVICE_REGISTRATION_FAILED, "Missing capabilities."
    if not isinstance(payload.get("capabilities"), list):
        return DEVICE_REGISTRATION_FAILED, "Malformed capabilities: must be a list."
    if payload.get("protocol_version") is None:
        return DEVICE_REGISTRATION_FAILED, "Missing protocol_version."
    if not is_supported_protocol_version(payload.get("protocol_version")):
        return DEVICE_REGISTRATION_FAILED, "Unsupported protocol version."
    return None, None


def build_device_error(
    error_code: str, message: str, request_id: str | None
) -> dict:
    """Build a DEVICE_ERROR payload envelope."""
    code = error_code if error_code in ERROR_CODES else COMMUNICATION_ERROR
    return {"error": code, "message": message, "request_id": request_id}


__all__ = [
    "DEVICE_REGISTER",
    "DEVICE_REGISTER_RESPONSE",
    "DEVICE_DISCOVER",
    "DEVICE_DISCOVER_RESPONSE",
    "DEVICE_INFO",
    "DEVICE_INFO_RESPONSE",
    "DEVICE_ERROR",
    "DEVICE_UNAVAILABLE",
    "DEVICE_NOT_FOUND",
    "DEVICE_ALREADY_REGISTERED",
    "DEVICE_NOT_REGISTERED",
    "DEVICE_REGISTRATION_FAILED",
    "INVALID_DESTINATION",
    "COMMUNICATION_ERROR",
    "ERROR_CODES",
    "DEVICE_STATUS_ONLINE",
    "DEVICE_STATUS_OFFLINE",
    "SUPPORTED_PROTOCOL_VERSION",
    "MINIMUM_TLS_VERSION",
    "REQUIRED_REGISTRATION_FIELDS",
    "is_supported_protocol_version",
    "validate_registration_payload",
    "build_device_error",
]
