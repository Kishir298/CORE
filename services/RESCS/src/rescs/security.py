"""API key authentication and owner/scope enforcement."""

from __future__ import annotations

import hmac

from fastapi import Depends, Header, Request

from rescs.api.deps import get_settings
from rescs.config import Settings
from rescs.errors import ForbiddenError, UnauthorizedError

SYSTEM_OWNER = "system"
DEVICE_PREFIX = "personal.device."

API_KEY_HEADER = "X-API-Key"


def authenticate_api_key(
    request: Request,
    settings: Settings = Depends(get_settings),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    """Verify the ``X-API-Key`` header and return the authenticated owner.

    A single shared key is configured via ``RESCS_API_KEY``. When
    ``RESCS_API_KEY_OWNER`` is set, requests are locked to that owner; the
    returned value is the principal later used for scoping.
    """
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.api_key):
        raise UnauthorizedError(
            f"a valid {API_KEY_HEADER} header is required",
            details={"header": API_KEY_HEADER},
        )
    return settings.api_key_owner or SYSTEM_OWNER


def enforce_owner(
    *,
    requested: str | None,
    principal: str,
    settings: Settings,
    field: str = "owner",
) -> str:
    """Resolve the effective owner for a write request, enforcing scope."""
    if settings.api_key_owner:
        if requested and requested != settings.api_key_owner:
            raise UnauthorizedError(
                f"cannot act as owner {requested!r}; locked to "
                f"{settings.api_key_owner!r}",
                details={field: requested},
            )
        return settings.api_key_owner
    return requested or principal


def scoped_query_owner(
    *,
    owner: str | None,
    principal: str,
    settings: Settings,
) -> str | None:
    """Resolve the owner filter for list requests, enforcing scope."""
    if settings.api_key_owner:
        if owner and owner != settings.api_key_owner:
            raise UnauthorizedError(
                f"cannot filter by owner {owner!r}; locked to "
                f"{settings.api_key_owner!r}",
                details={"owner": owner},
            )
        return settings.api_key_owner
    return owner or principal


def assert_principal_is_owner(
    *,
    record_owner: str,
    principal: str,
    settings: Settings,
) -> None:
    """Guard reads/deletes of another owner's resource when scoped."""
    if settings.api_key_owner and record_owner != settings.api_key_owner:
        raise ForbiddenError(
            f"this resource belongs to owner {record_owner!r}",
            details={"owner": record_owner},
        )


def require_api_key(principal: str = Depends(authenticate_api_key)) -> str:
    """FastAPI dependency marker for routes that must be authenticated."""
    return principal


def get_device_id(
    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
) -> str | None:
    """Extract device ID from ``X-Device-Id`` header if present."""
    return x_device_id


# ============================================================================
# Device-Scoped Access Validation
# ============================================================================

# Reserved namespace prefixes that cannot be accessed by devices
RESERVED_NAMESPACE_PREFIXES = ("core.", "rescs.", "asis.", "tiviss.")
# Device-scoped namespace prefix
DEVICE_NAMESPACE_PREFIX = "personal.device."


def validate_device_namespace(
    namespace: str,
    device_id: str,
    operation: str = "access",
) -> str:
    """
    Validate and transform a namespace for device-scoped access.
    
    Args:
        namespace: The requested namespace
        device_id: The requesting device's ID
        operation: Description of operation for error messages
        
    Returns:
        The validated (possibly transformed) namespace
        
    Raises:
        UnauthorizedError: If access is denied
    """
    # Check for reserved namespace access
    for prefix in RESERVED_NAMESPACE_PREFIXES:
        if namespace.startswith(prefix):
            raise UnauthorizedError(
                f"cannot {operation} reserved namespace '{namespace}'",
                details={"namespace": namespace, "device_id": device_id},
            )
    
    expected_prefix = f"{DEVICE_NAMESPACE_PREFIX}{device_id}."
    
    # If already device-scoped, verify it matches this device
    if namespace.startswith(DEVICE_NAMESPACE_PREFIX):
        if not namespace.startswith(expected_prefix):
            raise UnauthorizedError(
                f"cannot {operation} another device's namespace",
                details={"namespace": namespace, "device_id": device_id},
            )
        return namespace
    
    # Otherwise, prefix with device scope
    return f"{expected_prefix}{namespace}"


def validate_device_owner(
    owner: str | None,
    device_id: str,
    operation: str = "access",
) -> str | None:
    """
    Validate and transform an owner for device-scoped access.
    
    Args:
        owner: The requested owner (or None)
        device_id: The requesting device's ID
        operation: Description of operation for error messages
        
    Returns:
        The validated (possibly transformed) owner, or None
        
    Raises:
        UnauthorizedError: If access is denied
    """
    if owner is None:
        return None
    
    expected_prefix = f"{DEVICE_NAMESPACE_PREFIX}{device_id}"
    
    # If already device-scoped, verify it matches this device
    if owner.startswith(DEVICE_NAMESPACE_PREFIX):
        if not owner.startswith(expected_prefix):
            raise UnauthorizedError(
                f"cannot {operation} another device's owner scope",
                details={"owner": owner, "device_id": device_id},
            )
        return owner
    
    # Otherwise, prefix with device scope
    return f"{expected_prefix}.{owner}"


def extract_device_id_from_namespace(namespace: str) -> str | None:
    """Extract device_id from a device-scoped namespace, or None if not device-scoped."""
    if namespace.startswith(DEVICE_NAMESPACE_PREFIX):
        remainder = namespace[len(DEVICE_NAMESPACE_PREFIX):]
        device_id = remainder.split(".", 1)[0]
        return device_id if device_id else None
    return None


def assert_device_ownership(
    *,
    resource_owner: str,
    resource_namespace: str,
    device_id: str,
    operation: str = "access",
) -> None:
    """
    Assert that a resource belongs to the requesting device.
    
    Both owner and namespace must be device-scoped for the same device.
    """
    # Extract device_id from namespace
    ns_device_id = extract_device_id_from_namespace(resource_namespace)
    if ns_device_id != device_id:
        raise UnauthorizedError(
            f"cannot {operation} resource from different device",
            details={
                "resource_namespace": resource_namespace,
                "resource_owner": resource_owner,
                "device_id": device_id,
                "namespace_device_id": ns_device_id,
            },
        )
    
    # Verify owner matches device scope
    if not resource_owner.startswith(f"{DEVICE_NAMESPACE_PREFIX}{device_id}"):
        raise UnauthorizedError(
            f"cannot {operation} resource with mismatched owner scope",
            details={
                "resource_namespace": resource_namespace,
                "resource_owner": resource_owner,
                "device_id": device_id,
            },
        )
