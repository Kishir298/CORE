"""Audit service: persistent, secret-free operation log.

The audit trail records who did what to which resource, when, with what
outcome — never secrets, values, or bytes. Audit writes are best-effort:
a failing audit backend must not break the primary storage operation.
"""

from __future__ import annotations

import uuid

from rescs.domain import AuditData, Page, utcnow
from rescs.interfaces.repository import AuditRepository
from rescs.logging import get_logger

logger = get_logger(__name__)


class AuditService:
    def __init__(self, repository: AuditRepository) -> None:
        self._repo = repository

    def log(
        self,
        operation: str,
        *,
        resource_type: str = "",
        resource_id: str | None = None,
        owner: str = "system",
        outcome: str = "ok",
        error_code: str | None = None,
    ) -> None:
        """Append an audit event; never raises."""
        try:
            from rescs.observability import request_id_var

            request_id = request_id_var.get()
        except Exception:
            request_id = None
        event = AuditData(
            id=str(uuid.uuid4()),
            timestamp=utcnow(),
            operation=operation,
            resource_type=resource_type,
            resource_id=resource_id,
            owner=owner,
            request_id=request_id,
            outcome=outcome,
            error_code=error_code,
        )
        try:
            self._repo.append(event)
        except Exception as exc:
            logger.warning("audit append failed for %s: %s", operation, exc)

    def list(
        self,
        *,
        owner: str | None = None,
        operation: str | None = None,
        since=None,
        limit: int = 100,
        offset: int = 0,
    ) -> Page[AuditData]:
        from rescs.services.utils import clamp_pagination

        limit, offset = clamp_pagination(limit, offset)
        return self._repo.list(
            owner=owner, operation=operation, since=since, limit=limit, offset=offset
        )

    def prune_before(self, cutoff) -> int:
        return self._repo.prune_before(cutoff)

