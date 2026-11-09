"""
Confirmation handling for potentially dangerous A.S.I.S. operations.

Confirmation is a pluggable handler so the CLI app can prompt the user
while tests can inject a deterministic handler.
"""

from __future__ import annotations

from collections.abc import Callable

from asis.configuration.settings import settings
from asis.logging.logger import get_logger

from .models import PermissionLevel, requires_confirmation

ConfirmationHandler = Callable[[str, PermissionLevel], bool]


def request_confirmation(
    action: str,
    level: PermissionLevel,
    handler: ConfirmationHandler | None = None,
) -> bool:
    """
    Decide whether an operation may proceed.

    Safe/low-risk operations proceed automatically. Dangerous operations
    require explicit confirmation unless the "confirm dangerous tools"
    option is disabled. Returns True when approved.
    """
    if not requires_confirmation(level):
        return True

    if not settings.security.require_confirmation_for_dangerous:
        return True

    if handler is None:
        handler = build_console_confirmation()

    return handler(action, level)


def build_console_confirmation() -> ConfirmationHandler:
    """Return a handler that prompts the user on the console."""
    logger = get_logger("permissions.confirmation")

    def confirm(action: str, level: PermissionLevel) -> bool:
        print()
        print("A.S.I.S. security confirmation required.")
        print(f"Action: {action}")
        print(f"Risk level: {level.name}")
        print("Type 'yes' to continue.")

        try:
            response = input("> ").strip().lower()
            return response == "yes"

        except (EOFError, KeyboardInterrupt):
            logger.warning("Confirmation prompt aborted.")
            return False

    return confirm


def auto_approve() -> ConfirmationHandler:
    """Return a handler that always approves (test/demo helper)."""

    def approve(action: str, level: PermissionLevel) -> bool:
        return True

    return approve


def auto_deny() -> ConfirmationHandler:
    """Return a handler that always denies (test/demo helper)."""

    def deny(action: str, level: PermissionLevel) -> bool:
        return False

    return deny
