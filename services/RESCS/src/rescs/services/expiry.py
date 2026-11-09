"""Shared TTL / expiry resolution.

Converts ``expires_at`` / ``ttl_seconds`` inputs into a validated UTC
``expires_at`` timestamp, enforcing the configured maximum TTL.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from rescs.config import Settings
from rescs.domain import ensure_utc, utcnow
from rescs.errors import InvalidRequestError


def resolve_expiry(
    expires_at: datetime | None,
    ttl_seconds: int | None,
    settings: Settings | None,
) -> datetime | None:
    """Resolve ``expires_at``/``ttl_seconds`` to a future UTC datetime.

    - Both unset → ``None`` (no expiration).
    - Both set → handled at schema layer, but guarded here as well.
    - ``ttl_seconds`` → ``now + ttl``.
    - Enforces ``max_ttl_seconds`` (0 = unlimited).
    - Rejects past/present ``expires_at``.
    """
    if expires_at is not None and ttl_seconds is not None:
        raise InvalidRequestError(
            "set either expires_at or ttl_seconds, not both",
            details={},
        )
    now = utcnow()
    moment: datetime | None = None
    if ttl_seconds is not None:
        if ttl_seconds < 1:
            raise InvalidRequestError(
                "ttl_seconds must be >= 1",
                details={"ttl_seconds": ttl_seconds},
            )
        moment = now + timedelta(seconds=ttl_seconds)
    elif expires_at is not None:
        moment = ensure_utc(expires_at)
        assert moment is not None
        if moment <= now:
            raise InvalidRequestError(
                "expires_at must be in the future",
                details={"expires_at": moment.isoformat()},
            )
    if moment is None:
        return None
    max_ttl = settings.max_ttl_seconds if settings is not None else 31536000
    if max_ttl and (moment - now).total_seconds() > max_ttl:
        raise InvalidRequestError(
            f"requested TTL exceeds maximum of {max_ttl} seconds",
            details={"max_ttl_seconds": max_ttl},
        )
    return moment

