"""SQLAlchemy model for resumable upload sessions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from rescs.db.base import Base
from rescs.domain import UploadSessionData, ensure_utc, utcnow


class UploadSession(Base):
    __tablename__ = "upload_sessions"
    __table_args__ = (
        Index("ix_upload_sessions_owner", "owner"),
        Index("ix_upload_sessions_status", "status"),
        Index("ix_upload_sessions_expires_at", "expires_at"),
        Index("ix_upload_sessions_status_expires", "status", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner: Mapped[str] = mapped_column(String(256), nullable=False, default="system")
    filename: Mapped[str] = mapped_column(String(512), nullable=False, default="unnamed")
    content_type: Mapped[str] = mapped_column(String(128), nullable=False, default="application/octet-stream")
    total_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    received_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, default=8388608)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    meta: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    def to_domain(self) -> UploadSessionData:
        return UploadSessionData(
            id=self.id,
            owner=self.owner,
            filename=self.filename,
            content_type=self.content_type,
            total_size=self.total_size,
            received_bytes=self.received_bytes,
            chunk_size=self.chunk_size,
            status=self.status,
            checksum=self.checksum,
            created_at=ensure_utc(self.created_at),
            updated_at=ensure_utc(self.updated_at),
            expires_at=ensure_utc(self.expires_at),
            metadata=self.meta or {},
            tags=list(self.tags or []),
        )

    @classmethod
    def from_domain(cls, data: UploadSessionData) -> UploadSession:
        return cls(
            id=data.id,
            owner=data.owner,
            filename=data.filename,
            content_type=data.content_type,
            total_size=data.total_size,
            received_bytes=data.received_bytes,
            chunk_size=data.chunk_size,
            status=data.status,
            checksum=data.checksum,
            created_at=ensure_utc(data.created_at),
            updated_at=ensure_utc(data.updated_at),
            expires_at=ensure_utc(data.expires_at),
            meta=dict(data.metadata or {}),
            tags=list(data.tags or []),
        )

