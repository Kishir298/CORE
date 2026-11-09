"""
Tool authorization for A.S.I.S.
"""

from __future__ import annotations

from collections.abc import Callable

from asis.permissions.confirmation import ConfirmationHandler, request_confirmation

from .base import Tool

Authorizer = Callable[[Tool], bool]


def build_authorizer(
    handler: ConfirmationHandler | None = None,
) -> Authorizer:
    """Return an authorizer backed by a confirmation handler."""

    def authorize(tool: Tool) -> bool:
        return request_confirmation(
            action=tool.name,
            level=tool.permission,
            handler=handler,
        )

    return authorize
