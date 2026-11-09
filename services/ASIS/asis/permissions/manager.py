"""
Permission manager for A.S.I.S.

Thin object-oriented facade over the existing permission primitives
(``PermissionLevel``, ``requires_confirmation``, ``request_confirmation``
via ``tools.build_authorizer``). No new policy lives here: levels stay on
``Tool.metadata.permission`` and confirmation behavior stays in
``permissions.confirmation``. Exists so CORE tools (and future
capabilities) depend on a named ``PermissionManager`` rather than bare
callables, while every previously built authorizer keeps working.
"""

from __future__ import annotations

from asis.errors import PermissionError as ASISPermissionError
from asis.permissions.confirmation import ConfirmationHandler
from asis.permissions.models import PermissionLevel, requires_confirmation
from asis.tools.authorizer import Authorizer, build_authorizer
from asis.tools.base import Tool


class PermissionManager:
    """Named gate for tool execution decisions."""

    def __init__(
        self,
        handler: ConfirmationHandler | None = None,
        authorizer: Authorizer | None = None,
    ) -> None:
        self._authorizer = authorizer or build_authorizer(handler)

    @property
    def authorizer(self) -> Authorizer:
        """Expose the underlying callable for ToolExecutor compatibility."""
        return self._authorizer

    def allows(self, tool: Tool) -> bool:
        """Return whether a tool may execute (may prompt for confirmation)."""
        return bool(self._authorizer(tool))

    def level(self, tool: Tool) -> PermissionLevel:
        """Return the tool's declared permission level."""
        return tool.permission

    def needs_confirmation(self, tool: Tool) -> bool:
        """Return whether a tool requires confirmation before execution."""
        return requires_confirmation(tool.permission)

    def require(self, tool: Tool) -> None:
        """Raise on denial (ASIS ``PermissionError``)."""
        if not self.allows(tool):
            raise ASISPermissionError(f"Permission denied for tool: {tool.name}")
