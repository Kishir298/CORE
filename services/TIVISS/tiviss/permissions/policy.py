"""Permission policies: default-deny with explicit allow/deny rules.

The architectural principle is least privilege: the default is to deny
everything unless an explicit rule grants it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .permissions import Permission, PermissionContext, PermissionDeniedError


class PermissionPolicy(ABC):
    """Interface for deciding whether a permission is granted."""

    @abstractmethod
    def check(self, ctx: PermissionContext, permission: Permission) -> bool:
        """Return True when ``permission`` is granted for ``ctx``."""

    def assert_allowed(self, ctx: PermissionContext, permission: Permission) -> None:
        """Raise :class:`PermissionDeniedError` when the check fails."""
        if not self.check(ctx, permission):
            raise PermissionDeniedError(
                permission, source=ctx.source, context=self.__class__.__name__
            )


class DefaultDenyPolicy(PermissionPolicy):
    """Deterministic allow-list policy.

    Rules:
      1. An explicit deny wins (including patterns).
      2. An explicit allow wins (including patterns).
      3. Otherwise the permission is denied.
    """

    def __init__(
        self,
        *,
        allow: set[Permission] | None = None,
        deny: set[Permission] | None = None,
    ) -> None:
        self._allow: set[Permission] = set(allow or {})
        self._deny: set[Permission] = set(deny or {})

    def allow(self, permission: Permission | str) -> None:
        self._allow.add(
            permission
            if isinstance(permission, Permission)
            else Permission.of(permission)
        )

    def deny(self, permission: Permission | str) -> None:
        self._deny.add(
            permission
            if isinstance(permission, Permission)
            else Permission.of(permission)
        )

    def revoke_allow(self, permission: Permission | str) -> None:
        target = (
            permission
            if isinstance(permission, Permission)
            else Permission.of(permission)
        )
        self._allow.add(target)  # ensure normalized type
        self._allow.discard(target)

    @property
    def allowed(self) -> frozenset[str]:
        return frozenset(p.name for p in self._allow)

    @property
    def denied(self) -> frozenset[str]:
        return frozenset(p.name for p in self._deny)

    def check(self, ctx: PermissionContext, permission: Permission) -> bool:
        for rule in self._deny:
            if rule.matches(permission):
                return False
        return any(rule.matches(permission) for rule in self._allow)
