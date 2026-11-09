"""SQLAlchemy model for persistent audit events."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from rescs.db.base import Base
from rescs.domain import AuditData, ensure_utc, utcnow


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    operation: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    resource_id: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    owner: Mapped[str] = mapped_column(
        String(256), nullable=False, default="system", index=True
    )
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def to_domain(self) -> AuditData:
        return AuditData(
            id=self.id,
            timestamp=ensure_utc(self.timestamp),
            operation=self.operation,
            resource_type=self.resource_type,
            resource_id=self.resource_id,
            owner=self.owner,
            request_id=self.request_id,
            outcome=self.outcome,
            error_code=self.error_code,
        )

    @classmethod
    def from_domain(cls, data: AuditData) -> AuditEvent:
        return cls(
            id=data.id,
            timestamp=ensure_utc(data.timestamp),
            operation=data.operation,
            resource_type=data.resource_type,
            resource_id=data.resource_id,
            owner=data.owner,
            request_id=data.request_id,
            outcome=data.outcome,
            error_code=data.error_code,
        )

