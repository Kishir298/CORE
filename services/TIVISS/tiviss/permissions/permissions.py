"""Permission model: least-privilege, explicit, deterministic.

Permissions use a dot-namespaced name (e.g. ``memory.store``,
``tools:execute`` or ``handover.request``). Policies decide whether a
permission is granted for a given context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..identity import AgentIdentity


class PermissionValidationError(ValueError):
    """Raised when a permission name is malformed."""


@dataclass(frozen=True)
class Permission:
    """An explicit, namespaced permission.

    ``name`` may be a concrete permission (``memory.store``) or a wildcard
    pattern (``memory.*``).
    """

    name: str

    def __post_init__(self) -> None:
        name = self.name
        if not isinstance(name, str) or not name.strip():
            raise PermissionValidationError(
                "permission name must be a non-empty string"
            )
        parts = name.split(".")
        if not all(part.isidentifier() or part == "*" for part in parts):
            raise PermissionValidationError(
                f"permission name contains invalid parts: {name!r}"
            )
        if any(part == "*" for part in parts[:-1]):
            raise PermissionValidationError(
                f"wildcard is only allowed as the last part: {name!r}"
            )
        object.__setattr__(self, "name", name)

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"Permission({self.name!r})"

    def is_pattern(self) -> bool:
        return self.name.endswith(".*")

    def matches(self, concrete: Permission) -> bool:
        """True when this permission (or pattern) covers ``concrete``."""
        if "." not in self.name or not self.is_pattern():
            return self.name == concrete.name
        return concrete.name.startswith(self.name[:-1])

    @classmethod
    def of(cls, name: str) -> Permission:
        return cls(name=name)


class PermissionDeniedError(PermissionError):
    """Raised when an action is not permitted by policy."""

    def __init__(
        self, permission: Permission, *, source: str | None = None, context: str = ""
    ) -> None:
        self.permission = permission
        self.source = source
        self.context = context
        detail = f"permission denied: {permission}"
        if source:
            detail += f" for {source}"
        if context:
            detail += f" ({context})"
        super().__init__(detail)


@dataclass
class PermissionContext:
    """Who (or what) is making the request and under what agent identity."""

    source: str = "unknown"
    identity: AgentIdentity | None = None
    metadata: dict = field(default_factory=dict)
