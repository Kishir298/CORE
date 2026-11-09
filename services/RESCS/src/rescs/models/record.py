"""SQLAlchemy model for stored records (JSON-value storage cells)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from rescs.db.base import Base
from rescs.domain import RecordData, ensure_utc, utcnow


class Record(Base):
    __tablename__ = "records"
    __table_args__ = (
        # Live-only uniqueness: soft-deleted rows keep their (namespace, key)
        # for auditability but no longer reserve it. Dialects without partial
        # index support fall back to a plain unique index; the service layer
        # additionally guards live-key collisions at the application level.
        Index(
            "uq_records_live_namespace_key",
            "namespace",
            "key",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_records_owner_updated", "owner", "updated_at"),
        Index("ix_records_owner_expires", "owner", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(512), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    meta: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    owner: Mapped[str] = mapped_column(String(256), nullable=False, default="system")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True
    )
    etag: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    deleted_by: Mapped[str | None] = mapped_column(String(256), nullable=True)

    def to_domain(self) -> RecordData:
        return RecordData(
            id=self.id,
            namespace=self.namespace,
            key=self.key,
            value=self.value,
            metadata=self.meta or {},
            owner=self.owner,
            version=self.version,
            idempotency_key=self.idempotency_key,
            etag=self.etag,
            created_at=ensure_utc(self.created_at),
            updated_at=ensure_utc(self.updated_at),
            tags=list(self.tags or []),
            expires_at=ensure_utc(self.expires_at),
            deleted_at=ensure_utc(self.deleted_at),
            deleted_by=self.deleted_by,
        )

    @classmethod
    def from_domain(cls, data: RecordData) -> Record:
        return cls(
            id=data.id,
            namespace=data.namespace,
            key=data.key,
            value=data.value,
            meta=data.metadata,
            owner=data.owner,
            version=data.version,
            idempotency_key=data.idempotency_key,
            etag=data.etag,
            created_at=ensure_utc(data.created_at),
            updated_at=ensure_utc(data.updated_at),
            tags=list(data.tags or []),
            expires_at=ensure_utc(data.expires_at),
            deleted_at=ensure_utc(data.deleted_at),
            deleted_by=data.deleted_by,
        )
