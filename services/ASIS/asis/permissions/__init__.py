"""
A.S.I.S. security and permission subsystem.
"""

from .confirmation import (
    ConfirmationHandler,
    auto_approve,
    auto_deny,
    build_console_confirmation,
    request_confirmation,
)
from .models import PermissionLevel, requires_confirmation
from .sandbox import SandboxViolation, resolve_sandbox_path
from .secrets import get_secret, require_secret
from .validation import (
    require_non_empty_string,
    require_one_of,
    require_positive_integer,
)

__all__ = [
    "ConfirmationHandler",
    "PermissionLevel",
    "PermissionManager",
    "SandboxViolation",
    "auto_approve",
    "auto_deny",
    "build_console_confirmation",
    "get_secret",
    "request_confirmation",
    "require_non_empty_string",
    "require_one_of",
    "require_positive_integer",
    "require_secret",
    "requires_confirmation",
    "resolve_sandbox_path",
]


def __getattr__(name: str):
    """Lazily expose PermissionManager (avoids a tools/permissions cycle)."""
    if name == "PermissionManager":
        from .manager import PermissionManager

        return PermissionManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
