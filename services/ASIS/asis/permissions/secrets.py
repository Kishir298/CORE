"""
Secret handling for A.S.I.S.

Secrets come from the environment or another secure credential
provider, never from committed source code.
"""

from __future__ import annotations

import os

from asis.errors import ConfigurationError


def get_secret(name: str) -> str | None:
    """Retrieve a secret from an environment variable."""
    value = os.getenv(name)

    if value is None:
        return None

    value = value.strip()
    return value or None


def require_secret(name: str) -> str:
    """Retrieve a required secret or raise a configuration error."""
    value = get_secret(name)

    if value is None:
        raise ConfigurationError(f"Required secret '{name}' is not configured.")

    return value
