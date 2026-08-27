from core.errors import CoreError

from .models import Identity, Permission


class SecurityError(CoreError):
    """Base exception for security errors."""


class IdentityAlreadyRegistered(SecurityError):
    """Raised when an identity already exists."""


class IdentityNotFound(SecurityError):
    """Raised when an identity does not exist."""


class AuthenticationError(SecurityError):
    """Raised when authentication fails."""


class AuthorizationError(SecurityError):
    """Raised when an identity lacks permission."""


class SecurityManager:
    """Provides the security foundation for C.O.R.E."""

    def __init__(self) -> None:
        self._identities: dict[str, Identity] = {}

    def register_identity(self, identity: Identity) -> Identity:
        if identity.identity_id in self._identities:
            raise IdentityAlreadyRegistered(
                f"Identity already registered: {identity.identity_id}"
            )

        self._identities[identity.identity_id] = identity
        return identity

    def unregister_identity(self, identity_id: str) -> Identity:
        identity = self.get_identity(identity_id)
        del self._identities[identity_id]
        return identity

    def get_identity(self, identity_id: str) -> Identity:
        try:
            return self._identities[identity_id]
        except KeyError as exc:
            raise IdentityNotFound(
                f"Identity not found: {identity_id}"
            ) from exc

    def authenticate(self, identity_id: str) -> Identity:
        """
        Authenticate an identity.

        Credential verification will be implemented by a
        dedicated authentication provider later.
        """

        identity = self.get_identity(identity_id)

        return identity

    def authorize(
        self,
        identity_id: str,
        permission: Permission,
    ) -> bool:
        identity = self.get_identity(identity_id)

        if permission not in identity.permissions:
            raise AuthorizationError(
                f"Identity '{identity_id}' lacks permission "
                f"'{permission.value}'"
            )

        return True

    def has_permission(
        self,
        identity_id: str,
        permission: Permission,
    ) -> bool:
        identity = self.get_identity(identity_id)
        return permission in identity.permissions

    def list_identities(self) -> list[Identity]:
        return list(self._identities.values())

    def count(self) -> int:
        return len(self._identities)

    def clear(self) -> None:
        self._identities.clear()
