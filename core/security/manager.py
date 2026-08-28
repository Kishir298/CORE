from collections.abc import Callable
from datetime import datetime, timezone
from threading import RLock

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


SecurityEventHandler = Callable[[dict], None]


class SecurityManager:
    """
    Provides the security foundation for C.O.R.E.

    SecurityManager manages identities, permissions, authentication,
    authorization, and security activity metrics.
    """

    def __init__(self) -> None:
        self._identities: dict[str, Identity] = {}
        self._lock = RLock()
        self._active = True

        self._authentication_count = 0
        self._authentication_failures = 0
        self._authorization_count = 0
        self._authorization_failures = 0

        self._event_handlers: list[SecurityEventHandler] = []

    def start(self) -> None:
        """Start the security manager."""

        with self._lock:
            self._active = True

    def stop(self) -> None:
        """Stop the security manager."""

        with self._lock:
            self._active = False

    @property
    def is_running(self) -> bool:
        """Return whether the security manager is active."""

        with self._lock:
            return self._active

    def _require_active(self) -> None:
        """Ensure security operations are currently allowed."""

        if not self._active:
            raise SecurityError("Security manager is not running.")

    def _emit_event(
        self,
        event_type: str,
        identity_id: str,
        success: bool,
    ) -> None:
        """Notify registered security-event handlers."""

        event = {
            "event_type": event_type,
            "identity_id": identity_id,
            "success": success,
            "timestamp": datetime.now(timezone.utc),
        }

        with self._lock:
            handlers = list(self._event_handlers)

        for handler in handlers:
            try:
                handler(event)
            except Exception:
                # Security event observers must never break the security
                # operation that generated the event.
                continue

    def register_event_handler(
        self,
        handler: SecurityEventHandler,
    ) -> None:
        """Register a handler for security events."""

        if not callable(handler):
            raise TypeError("Security event handler must be callable.")

        with self._lock:
            if handler not in self._event_handlers:
                self._event_handlers.append(handler)

    def unregister_event_handler(
        self,
        handler: SecurityEventHandler,
    ) -> None:
        """Remove a security event handler."""

        with self._lock:
            if handler in self._event_handlers:
                self._event_handlers.remove(handler)

    def register_identity(self, identity: Identity) -> Identity:
        """Register a new identity."""

        with self._lock:
            self._require_active()

            if identity.identity_id in self._identities:
                raise IdentityAlreadyRegistered(
                    f"Identity already registered: {identity.identity_id}"
                )

            self._identities[identity.identity_id] = identity

        self._emit_event(
            "IDENTITY_REGISTERED",
            identity.identity_id,
            True,
        )

        return identity

    def unregister_identity(self, identity_id: str) -> Identity:
        """Remove and return an identity."""

        with self._lock:
            self._require_active()

            identity = self.get_identity(identity_id)
            del self._identities[identity_id]

        self._emit_event(
            "IDENTITY_UNREGISTERED",
            identity_id,
            True,
        )

        return identity

    def get_identity(self, identity_id: str) -> Identity:
        """Return a registered identity."""

        with self._lock:
            try:
                return self._identities[identity_id]
            except KeyError as exc:
                raise IdentityNotFound(
                    f"Identity not found: {identity_id}"
                ) from exc

    def authenticate(self, identity_id: str) -> Identity:
        """
        Authenticate an identity.

        Credential verification will be implemented by a dedicated
        authentication provider later.
        """

        with self._lock:
            self._require_active()

            self._authentication_count += 1

            try:
                identity = self.get_identity(identity_id)
            except IdentityNotFound:
                self._authentication_failures += 1

                self._emit_event(
                    "AUTHENTICATION_FAILED",
                    identity_id,
                    False,
                )

                raise

        self._emit_event(
            "AUTHENTICATION_SUCCEEDED",
            identity_id,
            True,
        )

        return identity

    def authorize(
        self,
        identity_id: str,
        permission: Permission,
    ) -> bool:
        """Verify that an identity has a specific permission."""

        with self._lock:
            self._require_active()

            self._authorization_count += 1

            try:
                identity = self.get_identity(identity_id)
            except IdentityNotFound:
                self._authorization_failures += 1

                self._emit_event(
                    "AUTHORIZATION_FAILED",
                    identity_id,
                    False,
                )

                raise

            if permission not in identity.permissions:
                self._authorization_failures += 1

                self._emit_event(
                    "AUTHORIZATION_FAILED",
                    identity_id,
                    False,
                )

                raise AuthorizationError(
                    f"Identity '{identity_id}' lacks permission "
                    f"'{permission.value}'"
                )

        self._emit_event(
            "AUTHORIZATION_SUCCEEDED",
            identity_id,
            True,
        )

        return True

    def has_permission(
        self,
        identity_id: str,
        permission: Permission,
    ) -> bool:
        """Return whether an identity has a permission."""

        with self._lock:
            self._require_active()

            identity = self.get_identity(identity_id)
            return permission in identity.permissions

    def list_identities(self) -> list[Identity]:
        """Return all registered identities."""

        with self._lock:
            return list(self._identities.values())

    def count(self) -> int:
        """Return the number of registered identities."""

        with self._lock:
            return len(self._identities)

    def authentication_count(self) -> int:
        """Return the number of authentication attempts."""

        with self._lock:
            return self._authentication_count

    def authentication_failure_count(self) -> int:
        """Return the number of failed authentication attempts."""

        with self._lock:
            return self._authentication_failures

    def authorization_count(self) -> int:
        """Return the number of authorization attempts."""

        with self._lock:
            return self._authorization_count

    def authorization_failure_count(self) -> int:
        """Return the number of failed authorization attempts."""

        with self._lock:
            return self._authorization_failures

    def clear(self) -> None:
        """Remove all identities and reset security state."""

        with self._lock:
            self._identities.clear()
            self._authentication_count = 0
            self._authentication_failures = 0
            self._authorization_count = 0
            self._authorization_failures = 0

    def reset_metrics(self) -> None:
        """Reset authentication and authorization metrics."""

        with self._lock:
            self._authentication_count = 0
            self._authentication_failures = 0
            self._authorization_count = 0
            self._authorization_failures = 0