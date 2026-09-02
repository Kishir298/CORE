from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import Identity


class AuthenticationProvider(ABC):
    """
    Pluggable credential verification for C.O.R.E.

    The default provider checks existence only, preserving the trusted
    internal flow. Token-based or future providers verify the supplied
    credential against identity metadata without hardcoding secrets.
    """

    @abstractmethod
    def authenticate(self, identity: Identity, credential: Any | None) -> bool:
        """
        Verify a credential for an identity.

        Return True when authentication succeeds; return False or raise
        AuthenticationError when it fails. The SecurityManager handles
        failure conversion and event emission.
        """


class ExistenceAuthenticationProvider(AuthenticationProvider):
    """
    Existence-only provider (default).

    Succeeds when the identity exists, regardless of credential. This keeps
    the internal routing spine unchanged until a real boundary is configured.
    """

    def authenticate(self, identity: Identity, credential: Any | None) -> bool:
        return True


class TokenAuthenticationProvider(AuthenticationProvider):
    """
    Token provider for Windows co-hosted deployment.

    If the identity carries ``metadata.token`` (or ``metadata.credential``),
    the supplied credential must equal that token. Identities without a token
    fall back to existence-only. This avoids hardcoded secrets while allowing
    per-identity bearer tokens supplied via message payload ``_credential`` or
    ``credential`` fields.
    """

    def authenticate(self, identity: Identity, credential: Any | None) -> bool:
        # Look for token in common metadata keys
        expected = None
        for key in ("token", "credential", "api_token", "password"):
            if key in identity.metadata:
                expected = identity.metadata[key]
                break

        # No token configured → existence suffices
        if expected is None:
            return True

        # Token configured → credential must match exactly
        return credential is not None and str(credential) == str(expected)


__all__ = [
    "AuthenticationProvider",
    "ExistenceAuthenticationProvider",
    "TokenAuthenticationProvider",
]
